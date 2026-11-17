import os, sqlite3, threading, webbrowser, datetime as dt
from functools import wraps
from urllib.parse import quote
from flask import (Flask, render_template, request, redirect, session, flash, url_for,
                   jsonify, g, has_request_context, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
app = Flask(__name__, static_folder=os.path.join(PUBLIC, "static"), static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", "changez-moi")
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
                  PERMANENT_SESSION_LIFETIME=dt.timedelta(days=30))

VILLES = ["Paris", "Lyon", "Marseille", "Toulouse", "Lille"]
CONTACT = {"tel": "+33 7 80 79 13 16", "tel_href": "tel:+33780791316", "whatsapp": "33780791316",
           "email": "contact@permis-express.local"}  # à modifier

@app.context_processor
def inject():
    wa = lambda t="Bonjour, une question sur Permis Express svp.": "https://wa.me/%s?text=%s" % (CONTACT["whatsapp"], quote(t))
    return {"contact": CONTACT, "villes_nav": VILLES, "wa": wa}

# ---------- Base de données : SQLite en local, PostgreSQL si DATABASE_URL existe (Vercel) ----------
PG_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
if PG_URL:
    import psycopg
    from psycopg.rows import dict_row
    INTEGRITY = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    INTEGRITY = (sqlite3.IntegrityError,)
SQLITE = "/tmp/permis.db" if os.environ.get("VERCEL") else os.path.join(BASE, "permis.db")

class DB:
    def __init__(self):
        self.pg = bool(PG_URL)
        if self.pg:
            self.c = psycopg.connect(PG_URL, row_factory=dict_row)
        else:
            self.c = sqlite3.connect(SQLITE); self.c.row_factory = sqlite3.Row
    def execute(self, q, a=()):
        if self.pg:
            cur = self.c.cursor(); cur.execute(q.replace("?", "%s"), tuple(a)); return cur
        return self.c.execute(q, a)
    def script(self, q):
        if self.pg: self.c.cursor().execute(q)
        else: self.c.executescript(q)
    def commit(self): self.c.commit()
    def rollback(self): self.c.rollback()
    def close(self):
        try: self.c.close()
        except Exception: pass

def db():
    if has_request_context():
        if "db" not in g: g.db = DB()
        return g.db
    return DB()

@app.teardown_appcontext
def close_db(e=None):
    d = g.pop("db", None)
    if d: d.close()

SCHEMA = """
create table if not exists users(id {pk}, name text, email text unique, pw text);
create table if not exists stages(id {pk}, city text, start text, price int, kind text, duration int default 10);
create table if not exists bookings(id {pk}, user_id int, stage_id int);
create table if not exists candidatures(id {pk}, name text, email text, city text, statut text);
create table if not exists messages(id {pk}, name text, email text, body text);"""

def next_monday():
    d = dt.date.today(); return d + dt.timedelta(days=(7 - d.weekday()) % 7 or 7)

def init():
    c = DB()
    c.script(SCHEMA.format(pk="serial primary key" if c.pg else "integer primary key")); c.commit()
    if c.pg:
        c.execute("alter table stages add column if not exists duration int default 10")
    else:
        try: c.execute("alter table stages add column duration int default 10")
        except sqlite3.OperationalError: pass
    c.commit()
    d = next_monday()
    if not c.execute("select 1 from stages where duration=10").fetchone():
        for i, city in enumerate(VILLES):
            for k in range(3):
                auto = k == 1
                c.execute("insert into stages(city,start,price,kind,duration) values(?,?,?,?,10)",
                          (city, (d + dt.timedelta(weeks=2 * k + i % 2)).isoformat(),
                           1590 if auto else 1490, "Boîte automatique" if auto else "Boîte manuelle"))
    if not c.execute("select 1 from stages where duration=14").fetchone():
        for i, city in enumerate(VILLES):
            for k in range(2):
                c.execute("insert into stages(city,start,price,kind,duration) values(?,?,?,?,14)",
                          (city, (d + dt.timedelta(weeks=3 * k + i % 2)).isoformat(),
                           1490 if k else 1390, "Boîte automatique" if k else "Boîte manuelle"))
    c.commit(); c.close()

def bdays(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d

def planning(start, n=10):
    d = dt.date.fromisoformat(start); out = []
    txt = "Conduite 2 h + code 1 h" if n == 10 else "Conduite 1 h 30 + code 1 h"
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d, "Examen blanc sur le centre d'examen" if len(out) >= n - 2 else txt))
        d += dt.timedelta(days=1)
    return out

app.jinja_env.filters["fr"] = lambda s: (dt.date.fromisoformat(s) if isinstance(s, str) else s).strftime("%d/%m/%Y")

def login(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            flash("Connectez-vous pour continuer."); return redirect(url_for("connexion"))
        return f(*a, **k)
    return w

# ---------- Pages ----------
@app.route("/")
def index(): return render_template("index.html")

@app.route("/stages")
def stages():
    v = request.args.get("ville", ""); n = request.args.get("duree", "")
    w, a = [], []
    if v: w.append("city=?"); a.append(v)
    if n in ("10", "14"): w.append("duration=?"); a.append(int(n))
    rows = db().execute("select * from stages" + (" where " + " and ".join(w) if w else "") + " order by start", a).fetchall()
    return render_template("stages.html", rows=rows, ville=v, duree=n, villes=VILLES)

@app.route("/reserver/<int:sid>", methods=["POST"])
@login
def reserver(sid):
    c = db()
    if not c.execute("select 1 from bookings where user_id=? and stage_id=?", (session["uid"], sid)).fetchone():
        c.execute("insert into bookings(user_id,stage_id) values(?,?)", (session["uid"], sid)); c.commit()
    flash("Stage réservé. Votre planning est prêt."); return redirect(url_for("espace"))

@app.route("/espace")
@login
def espace():
    rows = db().execute("select s.* from bookings b join stages s on s.id=b.stage_id where b.user_id=?",
                        (session["uid"],)).fetchall()
    data = []
    for r in rows:
        p = planning(r["start"], r["duration"] or 10)
        data.append((r, p, bdays(p[-1][0], 5)))
    return render_template("espace.html", data=data)

@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    if request.method == "POST":
        c = db(); email = request.form["email"].lower()
        try:
            c.execute("insert into users(name,email,pw) values(?,?,?)",
                      (request.form["name"], email, generate_password_hash(request.form["pw"]))); c.commit()
            uid = c.execute("select id from users where email=?", (email,)).fetchone()["id"]
            session.permanent = True; session.update(uid=uid, name=request.form["name"])
            return redirect(url_for("stages"))
        except INTEGRITY:
            c.rollback(); flash("Cet e-mail a déjà un compte. Connectez-vous.")
    return render_template("auth.html", mode="inscription")

@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if request.method == "POST":
        u = db().execute("select * from users where email=?", (request.form["email"].lower(),)).fetchone()
        if u and check_password_hash(u["pw"], request.form["pw"]):
            session.permanent = True; session.update(uid=u["id"], name=u["name"]); return redirect(url_for("espace"))
        flash("E-mail ou mot de passe incorrect.")
    return render_template("auth.html", mode="connexion")

@app.route("/deconnexion")
def deconnexion(): session.clear(); return redirect("/")

QUIZ = [
    ("Quelle est la vitesse maximale en agglomération ?", ["30 km/h", "50 km/h", "70 km/h"], 1),
    ("Que signifie un feu orange fixe ?", ["Accélérer", "S'arrêter si possible sans danger", "Priorité aux piétons"], 1),
    ("Distance de sécurité conseillée à 2 secondes d'intervalle ?", ["Oui, entre deux véhicules", "Non, 5 secondes", "Seulement sur autoroute"], 0),
    ("Le port de la ceinture est obligatoire…", ["À l'avant seulement", "À toutes les places équipées", "Hors agglomération"], 1),
    ("Taux d'alcool maximal pour un jeune conducteur ?", ["0,5 g/l", "0,2 g/l", "0,8 g/l"], 1),
    ("Que faire face à un véhicule de secours avec sirène ?", ["Accélérer", "Libérer le passage", "Klaxonner"], 1),
]

@app.route("/code")
def code(): return render_template("code.html", quiz=QUIZ)

@app.route("/financement")
def financement(): return render_template("financement.html")

@app.route("/moniteur", methods=["GET", "POST"])
def moniteur():
    if request.method == "POST":
        c = db(); c.execute("insert into candidatures(name,email,city,statut) values(?,?,?,?)",
            (request.form["name"], request.form["email"], request.form["city"], request.form["statut"])); c.commit()
        flash("Candidature reçue. Nous vous recontactons sous 48 h."); return redirect(url_for("moniteur"))
    return render_template("moniteur.html", villes=VILLES)

@app.route("/api/contact", methods=["POST"])
def api_contact():
    j = request.get_json(silent=True) or {}
    c = db(); c.execute("insert into messages(name,email,body) values(?,?,?)",
                        (j.get("name", ""), j.get("email", ""), "[Bulle] " + j.get("body", ""))); c.commit()
    return jsonify(ok=True)

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        c = db(); c.execute("insert into messages(name,email,body) values(?,?,?)",
            (request.form["name"], request.form["email"], "[" + request.form.get("sujet", "Question") + "] " + request.form["body"])); c.commit()
        flash("Message envoyé. Un conseiller vous répond vite."); return redirect(url_for("contact"))
    return render_template("contact.html")

# ---------- Application installable (PWA) ----------
@app.route("/offline")
def offline(): return render_template("offline.html")

@app.route("/sw.js")
def sw():
    r = send_from_directory(PUBLIC, "sw.js", mimetype="text/javascript"); r.headers["Cache-Control"] = "no-cache"; return r

@app.route("/manifest.webmanifest")
def manifest(): return send_from_directory(PUBLIC, "manifest.webmanifest", mimetype="application/manifest+json")

try: init()
except Exception as e: print("Initialisation de la base :", e)

if __name__ == "__main__":
    print("\n>>> Site lance sur http://127.0.0.1:5000  (Ctrl+C pour arreter)\n")
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
