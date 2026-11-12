import os, json, math, re, collections
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOK = re.compile(r"[a-z0-9]+")
STOP = set("the a an of to in is are and or for on with what how why does do did which that this it by as be from at its their".split())
toks = lambda s: [w for w in TOK.findall(s.lower()) if w not in STOP]
# setting name -> (piece size in words, pieces returned, rerank)
SETTINGS = {"S1_80w_k3": (80, 3, False), "S2_200w_k4": (200, 4, False), "S3_200w_k4_rerank": (200, 4, True), "S4_400w_k2": (400, 2, False)}

class Index:
    def __init__(self, size):
        pages_file = os.path.join(BASE_DIR, "data", "pages.json")
        with open(pages_file, "r", encoding="utf-8") as f:
            pages = json.load(f)
        step = max(1, int(size * 0.8)); self.chunks = []
        for p in pages:
            w = p["text"].split()
            for i in range(0, max(1, len(w)), step):
                seg = " ".join(w[i:i + size])
                if len(seg.split()) >= 15:
                    self.chunks.append(dict(paper=p["paper"], arxiv=p["arxiv"], page=p["page"], text=seg, tf=collections.Counter(toks(seg))))
        N = len(self.chunks); df = collections.Counter()
        for c in self.chunks: df.update(c["tf"].keys())
        self.idf = {t: math.log(1 + (N - n + .5) / (n + .5)) for t, n in df.items()}
        self.avg = sum(sum(c["tf"].values()) for c in self.chunks) / max(N, 1)

    def score(self, q, c):
        L = sum(c["tf"].values()); s = 0
        for t in q:
            f = c["tf"].get(t, 0)
            if f: s += self.idf.get(t, 0) * f * 2.2 / (f + 1.2 * (.25 + .75 * L / self.avg))
        return s

    def search(self, query, k, rerank, cov_q=None):
        q = toks(query); cq = set(toks(cov_q or query))
        ranked = sorted(((self.score(q, c), c) for c in self.chunks), key=lambda x: -x[0])[:k * 3 if rerank else k]
        if rerank:
            qb = set(zip(q, q[1:]))
            def r(x):
                s, c = x; t = toks(c["text"])
                return s * (1 + sum(w in c["tf"] for w in cq) / max(len(cq), 1)) + 3 * len(qb & set(zip(t, t[1:])))
            ranked = sorted(ranked, key=lambda x: -r(x))[:k]
        return [dict({a: b for a, b in c.items() if a != "tf"}, score=s, cov=sum(w in c["tf"] for w in cq) / max(len(cq), 1)) for s, c in ranked if s > 0]

_cache = {}
def get_index(size):
    if size not in _cache: _cache[size] = Index(size)
    return _cache[size]
