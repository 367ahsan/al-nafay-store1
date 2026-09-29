from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
import sqlite3, json, os, datetime, mimetypes, hmac, hashlib, secrets, time

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('ALNAFAY_DB') or os.path.join(BASE, 'alnafay.db')
DATA = os.path.dirname(os.path.abspath(DB))
MEDIA = os.path.join(BASE, 'media')
HOST = os.environ.get('HOST', '0.0.0.0'); PORT = int(os.environ.get('PORT', '5000'))
SESSION_DAYS = 7
FAILS = {}; ORDERS = {}          # ip -> list of timestamps (login failures / orders placed)

# ---------- admin password + signing key ----------
def load_secrets():
    pw = os.environ.get('ALNAFAY_ADMIN_PASSWORD', '').strip()
    pwfile = os.path.join(DATA, 'admin_password.txt')
    if not pw and os.path.isfile(pwfile):
        pw = open(pwfile, encoding='utf-8').read().strip()
    if not pw:
        pw = secrets.token_urlsafe(9)
        open(pwfile, 'w', encoding='utf-8').write(pw + '\n')
        print('\n  ADMIN PASSWORD (first run): ' + pw + '\n  Saved in admin_password.txt - open that file to see or change it.\n')
    keyfile = os.path.join(DATA, 'secret.key')
    if os.path.isfile(keyfile): key = open(keyfile, 'rb').read()
    else:
        key = secrets.token_bytes(32); open(keyfile, 'wb').write(key)
    return pw, key
ADMIN_PW, SECRET = '', b''

def sign(exp):
    return hmac.new(SECRET, f'{exp}:{hashlib.sha256(ADMIN_PW.encode()).hexdigest()}'.encode(), hashlib.sha256).hexdigest()
def make_token():
    exp = int(time.time()) + SESSION_DAYS * 86400; return f'{exp}.{sign(exp)}'
def check_token(t):
    try:
        exp, sig = t.split('.', 1)
        return int(exp) > time.time() and hmac.compare_digest(sig, sign(int(exp)))
    except Exception:
        return False

def hits(store, ip, window):
    now = time.time(); lst = [t for t in store.get(ip, []) if now - t < window]; store[ip] = lst; return lst

# ---------- database ----------
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init_db():
    c = db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,code TEXT DEFAULT '',fabric TEXT DEFAULT '',color TEXT DEFAULT '',thaan REAL DEFAULT 0,suit REAL DEFAULT 0,sale_thaan REAL DEFAULT 0,sale_suit REAL DEFAULT 0,image TEXT DEFAULT '',description TEXT DEFAULT '',sale_on INTEGER DEFAULT 0,new_arrival INTEGER DEFAULT 0,stock INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,product_id INTEGER DEFAULT 0,product TEXT DEFAULT '',tone TEXT DEFAULT '',option TEXT DEFAULT '',unit_price REAL DEFAULT 0,quantity INTEGER DEFAULT 1,total REAL DEFAULT 0,name TEXT DEFAULT '',email TEXT DEFAULT '',phone TEXT DEFAULT '',city TEXT DEFAULT '',address TEXT DEFAULT '',note TEXT DEFAULT '',status TEXT DEFAULT 'Pending');
    CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT,tagline TEXT,wa TEXT,phone TEXT,ig TEXT);
    ''')
    if c.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        imgs = json.dumps(['/media/fabric_1.png', '/media/fabric_2.png', '/media/fabric_3.png', '/media/fabric_4.png'])
        c.execute('''INSERT INTO products(name,code,fabric,color,thaan,suit,sale_thaan,sale_suit,image,description,sale_on,new_arrival,stock) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', ('Premium Black', 'AN-SC-BLK-001', 'Premium Gents Unstitched', 'Black', 3843, 5243, 0, 0, imgs, 'Premium black fabric. Four product views are shown on the card and product page.', 0, 1, 1))
    if c.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0: c.execute('INSERT INTO settings(id,name,tagline) VALUES(1,?,?)', ('AL NAFAY', 'Quality · Comfort · Style'))
    if 'items' not in [r[1] for r in c.execute('PRAGMA table_info(orders)')]: c.execute("ALTER TABLE orders ADD COLUMN items TEXT DEFAULT ''")
    c.commit(); c.close()

def product_dict(r):
    d = dict(r); d['sale_on'] = bool(d['sale_on']); d['new_arrival'] = bool(d['new_arrival']); d['stock'] = bool(d['stock']); return d

def clip(v, n): return str(v or '').strip()[:n]

# ---------- http helpers ----------
def send_json(h, obj, status=200, cookie=None):
    raw = json.dumps(obj, ensure_ascii=False).encode(); h.send_response(status)
    h.send_header('Content-Type', 'application/json; charset=utf-8'); h.send_header('Content-Length', str(len(raw)))
    h.send_header('Cache-Control', 'no-store'); h.send_header('X-Content-Type-Options', 'nosniff')
    if cookie: h.send_header('Set-Cookie', cookie)
    h.end_headers(); h.wfile.write(raw)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def ip(self): return self.headers.get('X-Forwarded-For', '').split(',')[0].strip() or self.client_address[0]
    def secure(self): return self.headers.get('X-Forwarded-Proto', '') == 'https'
    def is_admin(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == 'an_admin': return check_token(v)
        return False
    def need_admin(self):
        if self.is_admin(): return True
        send_json(self, {'error': 'Login required'}, 401); return False
    def body(self, limit):
        try: n = int(self.headers.get('Content-Length', '0') or 0)
        except ValueError: n = -1
        if n < 0 or n > limit: send_json(self, {'error': 'Request too large'}, 413); return None
        try: return json.loads(self.rfile.read(n) or b'{}')
        except Exception: send_json(self, {'error': 'Bad request'}, 400); return None
    def cookie(self, value, age):
        return f"an_admin={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}" + ('; Secure' if self.secure() else '')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/products':
            c = db(); rows = c.execute('SELECT * FROM products ORDER BY id').fetchall(); c.close(); return send_json(self, [product_dict(r) for r in rows])
        if path == '/api/settings':
            c = db(); r = c.execute('SELECT * FROM settings WHERE id=1').fetchone(); c.close(); return send_json(self, dict(r) if r else {})
        if path == '/api/orders':
            if not self.need_admin(): return
            c = db(); rows = c.execute('SELECT * FROM orders ORDER BY id DESC').fetchall(); c.close(); return send_json(self, [dict(r) for r in rows])
        if path == '/api/customers':
            if not self.need_admin(): return
            c = db(); rows = c.execute("SELECT name,phone,email,city,address,COUNT(*) order_count,MAX(created_at) last_order_at FROM orders WHERE name<>'' GROUP BY name,phone,email,city,address ORDER BY last_order_at DESC").fetchall(); c.close(); return send_json(self, [dict(r) for r in rows])
        if path == '/api/admin/me': return send_json(self, {'admin': self.is_admin()})
        if path == '/': return self.serve_file(os.path.join(BASE, 'website.html'))
        if path in ('/admin', '/admin/'): return self.serve_file(os.path.join(BASE, 'admin.html' if self.is_admin() else 'admin_login.html'))
        if path.startswith('/media/'): return self.serve_file(os.path.join(MEDIA, unquote(path[len('/media/'):])), MEDIA)
        return send_json(self, {'error': 'Not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/admin/login':
            ip = self.ip()
            if len(hits(FAILS, ip, 300)) >= 5: return send_json(self, {'error': 'Too many wrong attempts. Try again in 5 minutes.'}, 429)
            d = self.body(2000)
            if d is None: return
            if hmac.compare_digest(str(d.get('password', '')).encode(), ADMIN_PW.encode()):
                FAILS.pop(ip, None); return send_json(self, {'ok': True}, cookie=self.cookie(make_token(), SESSION_DAYS * 86400))
            FAILS[ip].append(time.time()); return send_json(self, {'error': 'Wrong password'}, 401)
        if path == '/api/admin/logout': return send_json(self, {'ok': True}, cookie=self.cookie('', 0))
        if path == '/api/orders':
            ip = self.ip()
            if len(hits(ORDERS, ip, 3600)) >= 15: return send_json(self, {'error': 'Too many orders from this connection. Please call us.'}, 429)
            d = self.body(200000)
            if d is None: return
            if not clip(d.get('name'), 100) or not clip(d.get('phone'), 40): return send_json(self, {'error': 'Name and phone are required'}, 400)
            c = db(); now = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
            raw = d.get('items') or [{'product_id': d.get('product_id', 0), 'product': d.get('product', ''), 'tone': d.get('tone', ''), 'option': d.get('option', ''), 'unit_price': d.get('unit_price', 0), 'quantity': d.get('quantity', 1)}]
            if not isinstance(raw, list) or len(raw) > 50: c.close(); return send_json(self, {'error': 'Invalid items'}, 400)
            items = []
            try:
                for i in raw:
                    pid = int(i.get('product_id') or 0); opt = clip(i.get('option'), 60); price = float(i.get('unit_price') or 0)
                    p = c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
                    if p:
                        suit = 'suit' in opt.lower(); reg = p['suit'] if suit else p['thaan']; sale = p['sale_suit'] if suit else p['sale_thaan']
                        price = sale if (p['sale_on'] and sale > 0) else reg
                    items.append({'product_id': pid, 'product': clip(i.get('product') or (p['name'] if p else ''), 120), 'tone': clip(i.get('tone'), 60), 'option': opt, 'unit_price': price, 'quantity': min(1000, max(1, int(i.get('quantity') or 1)))})
            except Exception:
                c.close(); return send_json(self, {'error': 'Invalid items'}, 400)
            total = sum(i['unit_price'] * i['quantity'] for i in items); qty = sum(i['quantity'] for i in items)
            names = ', '.join(dict.fromkeys(i['product'] for i in items)); opts = ', '.join(dict.fromkeys(i['option'] for i in items))
            cur = c.execute('''INSERT INTO orders(created_at,product_id,product,tone,option,unit_price,quantity,total,name,email,phone,city,address,note,status,items) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (now, items[0]['product_id'], names, items[0]['tone'], opts, items[0]['unit_price'] if len(items) == 1 else 0, qty, total, clip(d.get('name'), 100), clip(d.get('email'), 100), clip(d.get('phone'), 40), clip(d.get('city'), 80), clip(d.get('address'), 400), clip(d.get('note'), 500), 'Pending', json.dumps(items, ensure_ascii=False)))
            c.commit(); r = c.execute('SELECT * FROM orders WHERE id=?', (cur.lastrowid,)).fetchone(); c.close()
            ORDERS.setdefault(ip, []).append(time.time()); return send_json(self, dict(r), 201)
        if path == '/api/products':
            if not self.need_admin(): return
            d = self.body(30000000)
            if d is None: return
            c = db(); cur = c.execute('''INSERT INTO products(name,code,fabric,color,thaan,suit,sale_thaan,sale_suit,image,description,sale_on,new_arrival,stock) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (d.get('name', 'Unnamed Product'), d.get('code', ''), d.get('fabric', ''), d.get('color', ''), d.get('thaan', 0), d.get('suit', 0), d.get('sale_thaan', 0), d.get('sale_suit', 0), d.get('image', ''), d.get('description', ''), int(bool(d.get('sale_on'))), int(bool(d.get('new_arrival'))), int(bool(d.get('stock', True))))); c.commit(); r = c.execute('SELECT * FROM products WHERE id=?', (cur.lastrowid,)).fetchone(); c.close(); return send_json(self, product_dict(r), 201)
        if path == '/api/settings':
            if not self.need_admin(): return
            d = self.body(20000)
            if d is None: return
            c = db(); c.execute('INSERT INTO settings(id,name,tagline,wa,phone,ig) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,tagline=excluded.tagline,wa=excluded.wa,phone=excluded.phone,ig=excluded.ig', (d.get('name', 'AL NAFAY'), d.get('tagline', 'Quality · Comfort · Style'), d.get('wa', ''), d.get('phone', ''), d.get('ig', ''))); c.commit(); r = c.execute('SELECT * FROM settings WHERE id=1').fetchone(); c.close(); return send_json(self, dict(r))
        return send_json(self, {'error': 'Not found'}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if not self.need_admin(): return
        if path.startswith('/api/products/'):
            d = self.body(30000000)
            if d is None: return
            pid = int(path.rsplit('/', 1)[1]); fields = ['name', 'code', 'fabric', 'color', 'thaan', 'suit', 'sale_thaan', 'sale_suit', 'image', 'description', 'sale_on', 'new_arrival', 'stock']; vals = []
            c = db()
            if not c.execute('SELECT 1 FROM products WHERE id=?', (pid,)).fetchone(): c.close(); return send_json(self, {'error': 'Product not found'}, 404)
            for f in fields:
                v = d.get(f); v = int(bool(v)) if f in ('sale_on', 'new_arrival', 'stock') else v; vals.append(v)
            c.execute('UPDATE products SET ' + ','.join(f + '=?' for f in fields) + ' WHERE id=?', vals + [pid]); c.commit(); r = c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone(); c.close(); return send_json(self, product_dict(r))
        if path.startswith('/api/orders/'):
            d = self.body(2000)
            if d is None: return
            oid = int(path.rsplit('/', 1)[1]); status = d.get('status', 'Pending')
            if status not in ('Pending', 'Confirmed', 'Completed', 'Cancelled'): return send_json(self, {'error': 'Invalid status'}, 400)
            c = db(); c.execute('UPDATE orders SET status=? WHERE id=?', (status, oid)); c.commit(); r = c.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone(); c.close(); return send_json(self, dict(r) if r else {'error': 'Order not found'}, 200 if r else 404)
        return send_json(self, {'error': 'Not found'}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self.need_admin(): return
        if path.startswith('/api/products/'):
            pid = int(path.rsplit('/', 1)[1]); c = db(); c.execute('DELETE FROM products WHERE id=?', (pid,)); c.commit(); c.close(); return send_json(self, {'ok': True})
        return send_json(self, {'error': 'Not found'}, 404)

    def serve_file(self, full, root=None):
        full = os.path.realpath(full)
        if root and not full.startswith(os.path.realpath(root) + os.sep): return send_json(self, {'error': 'File not found'}, 404)
        if not os.path.isfile(full): return send_json(self, {'error': 'File not found'}, 404)
        data = open(full, 'rb').read(); typ = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        self.send_response(200); self.send_header('Content-Type', typ + ('; charset=utf-8' if typ.startswith('text/') else '')); self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff'); self.send_header('Referrer-Policy', 'same-origin')
        if full.endswith('.html'): self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(data)

if __name__ == '__main__':
    ADMIN_PW, SECRET = load_secrets(); init_db()
    print(f'AL NAFAY running at http://localhost:{PORT}  (admin: /admin)'); ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
