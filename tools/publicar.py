"""Publica no Instagram os posts da agenda.json que já chegaram no horário.

Uso:
  python3 tools/publicar.py           publica o que estiver no horário
  python3 tools/publicar.py --teste   só confere token, conta e arquivos (não publica nada)

Variáveis de ambiente: IG_TOKEN (secret), IG_USER_ID, BASE_URL (endereço do GitHub Pages).
O token nunca é impresso.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

API = "https://graph.instagram.com" + (("/" + os.environ["API_VERSION"]) if os.environ.get("API_VERSION") else "")
TOKEN = os.environ.get("IG_TOKEN", "")
IG = os.environ.get("IG_USER_ID", "")
BASE = os.environ.get("BASE_URL", "").rstrip("/") + "/"
AGENDA = os.path.join(os.path.dirname(__file__), "..", "agenda.json")
JANELA = timedelta(hours=12)  # post atrasado mais que isso não sai sozinho


class ApiErro(Exception):
    pass


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
            msg = f"{err.get('message')} (code {err.get('code')}/{err.get('error_subcode')})"
        except Exception:
            msg = f"HTTP {e.code}"
        raise ApiErro(msg.replace(TOKEN, "***") if TOKEN else msg) from None


def esperar(cid, minutos=10):
    fim = time.time() + minutos * 60
    while time.time() < fim:
        st = call("GET", cid, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise ApiErro(f"processamento falhou: {st.get('status')}")
        time.sleep(10)
    raise ApiErro("tempo esgotado esperando o Instagram processar a mídia")


def url(p):
    return BASE + p


def criar_container(post):
    t = post["tipo"]
    if t == "REELS":
        p = dict(media_type="REELS", video_url=url(post["video"]), caption=post["legenda"], share_to_feed="true")
        if post.get("capa"):
            p["cover_url"] = url(post["capa"])
        if post.get("teste"):
            p["trial_params"] = json.dumps({"graduation_strategy": "MANUAL"})
        cid = call("POST", f"{IG}/media", **p)["id"]
        esperar(cid)
        return cid
    if t == "IMAGE":
        cid = call("POST", f"{IG}/media", image_url=url(post["imagens"][0]), caption=post["legenda"])["id"]
        esperar(cid, 3)
        return cid
    if t == "CAROUSEL":
        filhos = []
        for im in post["imagens"]:
            filhos.append(call("POST", f"{IG}/media", image_url=url(im), is_carousel_item="true")["id"])
        for f in filhos:
            esperar(f, 3)
        cid = call("POST", f"{IG}/media", media_type="CAROUSEL", children=",".join(filhos), caption=post["legenda"])["id"]
        esperar(cid, 3)
        return cid
    raise ApiErro(f"tipo desconhecido: {t}")


def publicar(post):
    try:
        cid = criar_container(post)
    except ApiErro as e:
        if post.get("teste") and post.get("plano_b"):
            # Reel de teste recusado: vira Reel normal no plano B (2 dias depois, 19h30)
            post.update(teste=False, at=post.pop("plano_b"), obs=f"Reel de teste recusado ({e}); remarcado como Reel normal")
            print(f"  ↻ {post['id']}: {post['obs']} para {post['at']}")
            return "remarcado"
        raise
    mid = call("POST", f"{IG}/media_publish", creation_id=cid)["id"]
    post["media_id"] = mid
    try:
        post["link"] = call("GET", mid, fields="permalink").get("permalink")
    except ApiErro:
        pass
    if post.get("comentario"):
        try:
            call("POST", f"{mid}/comments", message=post["comentario"])
            post["obs"] = "comentário publicado; fixe pelo app"
        except ApiErro as e:
            post["obs"] = f"post ok, comentário não saiu ({e})"
    return "publicado"


def head(u):
    req = urllib.request.Request(u, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def teste(agenda):
    ok = True
    me = call("GET", "me", fields="user_id,username,account_type")
    print(f"✓ token válido: @{me.get('username')} ({me.get('account_type')}), user_id {me.get('user_id')}")
    if str(me.get("user_id")) != IG:
        print(f"✗ IG_USER_ID ({IG}) diferente do user_id da conta ({me.get('user_id')})"); ok = False
    try:
        lim = call("GET", f"{IG}/content_publishing_limit", fields="quota_usage,config")
        print(f"✓ limite de publicação: {lim.get('data', [{}])[0]}")
    except ApiErro as e:
        print(f"! não consegui ler o limite de publicação: {e}")
    pend = [p for p in agenda["posts"] if p["status"] == "agendado"]
    print(f"\nConferindo arquivos de {len(pend)} posts agendados em {BASE}")
    for p in pend:
        arqs = [p["video"], p.get("capa")] if p["tipo"] == "REELS" else p["imagens"]
        for a in filter(None, arqs):
            st, ct = head(url(a))
            esperado = "video/mp4" if a.endswith(".mp4") else "image/jpeg"
            if st != 200 or esperado not in ct:
                print(f"✗ {a}: {st} {ct}"); ok = False
    print("✓ arquivos acessíveis" if ok else "✗ há arquivos com problema")
    # cria (sem publicar) um contêiner de imagem para provar a permissão de publicação; ele expira sozinho em 24h
    img = next((p["imagens"][0] for p in pend if p["tipo"] != "REELS"), None)
    if img:
        try:
            cid = call("POST", f"{IG}/media", image_url=url(img), caption="teste (não publicado)")["id"]
            print(f"✓ permissão de publicação ok (contêiner de teste {cid} criado e NÃO publicado)")
        except ApiErro as e:
            print(f"✗ permissão de publicação: {e}"); ok = False
    print("\nPróximos posts:")
    for p in pend[:6]:
        print(f"  {p['at'][:16].replace('T', ' ')}  {p['tipo']:<8} {'(teste) ' if p.get('teste') else ''}{p['titulo']}")
    return ok


def main():
    agenda = json.load(open(AGENDA, encoding="utf-8"))
    agora = datetime.now(timezone.utc)
    devidos = [p for p in agenda["posts"] if p["status"] == "agendado" and datetime.fromisoformat(p["at"]) <= agora]
    if "--teste" not in sys.argv and not devidos:
        print("nada no horário agora"); return
    if not TOKEN or not IG or not BASE.startswith("https://"):
        sys.exit("faltam IG_TOKEN, IG_USER_ID ou BASE_URL")
    if "--teste" in sys.argv:
        sys.exit(0 if teste(agenda) else 1)
    falhas = 0
    for post in agenda["posts"]:
        if post["status"] != "agendado":
            continue
        quando = datetime.fromisoformat(post["at"])
        if quando > agora:
            continue
        if agora - quando > JANELA:
            post["status"] = "atrasado"
            post["obs"] = "passou do horário sem publicar; reagende mudando 'at' e voltando o status para 'agendado'"
            print(f"! {post['id']}: atrasado demais, não publicado")
            continue
        print(f"→ {post['id']} ({post['tipo']}) marcado para {post['at']}")
        try:
            r = publicar(post)
            if r == "publicado":
                post["status"] = "publicado"
                post["publicado_em"] = agora.astimezone(quando.tzinfo).isoformat(timespec="minutes")
                print(f"  ✓ publicado {post.get('link', '')}")
        except ApiErro as e:
            falhas += 1
            post["tentativas"] = post.get("tentativas", 0) + 1
            post["erro"] = str(e)
            if post["tentativas"] >= 3:
                post["status"] = "erro"
            print(f"  ✗ falhou (tentativa {post['tentativas']}): {e}")
        json.dump(agenda, open(AGENDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
