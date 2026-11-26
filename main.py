from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3, secrets, hashlib, hmac, os, json

ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv('MENUFLOW_DB_PATH',str(ROOT/'menuflow.db')))
app=FastAPI(title='MenuFlow Multi-restaurante',version='3.0-integrado')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def now(): return datetime.now().isoformat(timespec='seconds')
def pw_hash(pw,salt=None):
 salt=salt or secrets.token_hex(16); return salt+':'+hashlib.pbkdf2_hmac('sha256',pw.encode(),salt.encode(),180000).hex()
def verify(pw,stored):
 try: salt,h=stored.split(':',1); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',pw.encode(),salt.encode(),180000).hex(),h)
 except: return False
def init():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,phone TEXT DEFAULT '',password_hash TEXT NOT NULL,role TEXT NOT NULL,restaurant_id INTEGER,status TEXT NOT NULL DEFAULT 'Ativo',created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS restaurants(id INTEGER PRIMARY KEY,name TEXT NOT NULL,owner TEXT NOT NULL,email TEXT NOT NULL,phone TEXT DEFAULT '',address TEXT DEFAULT '',status TEXT NOT NULL DEFAULT 'Pendente',created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,name TEXT NOT NULL,category TEXT DEFAULT 'Geral',price REAL NOT NULL,description TEXT DEFAULT '',ingredients TEXT DEFAULT '',prep_minutes INTEGER DEFAULT 15,available INTEGER DEFAULT 1,FOREIGN KEY(restaurant_id) REFERENCES restaurants(id));
  CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,customer_id INTEGER,customer TEXT NOT NULL,items_json TEXT NOT NULL,total REAL NOT NULL,status TEXT NOT NULL DEFAULT 'Aguardando',prep_minutes INTEGER DEFAULT 15,created_at TEXT NOT NULL,FOREIGN KEY(restaurant_id) REFERENCES restaurants(id));
  CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
  CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,name TEXT NOT NULL,category TEXT DEFAULT '',quantity REAL DEFAULT 0,minimum REAL DEFAULT 0,expiry TEXT DEFAULT '',FOREIGN KEY(restaurant_id) REFERENCES restaurants(id));
  CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,stock_id INTEGER,kind TEXT,quantity REAL,note TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,name TEXT NOT NULL,role TEXT,phone TEXT,shift TEXT,hire_date TEXT,status TEXT DEFAULT 'Ativo');
  CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,order_id INTEGER,customer TEXT,amount REAL,method TEXT,status TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,restaurant_id INTEGER NOT NULL,description TEXT,amount REAL,created_at TEXT);
  ''')
  support_email=os.getenv('MENUFLOW_SUPPORT_EMAIL','support@menuflow.local').lower(); support_pw=os.getenv('MENUFLOW_SUPPORT_PASSWORD','ChangeMe-2026!')
  if not c.execute('SELECT id FROM users WHERE email=?',(support_email,)).fetchone(): c.execute('INSERT INTO users(name,email,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?)',('MenuFlow Suporte',support_email,pw_hash(support_pw),'support','Ativo',now()))
init()
class Register(BaseModel): name:str; email:str; password:str=Field(min_length=8); phone:str=''
class RestaurantRequest(BaseModel): name:str; owner:str; email:str; password:str=Field(min_length=8); phone:str=''; address:str=''
class Login(BaseModel): email:str; password:str
class ProductIn(BaseModel): name:str; category:str='Geral'; price:float=Field(ge=0); description:str=''; ingredients:str=''; prep_minutes:int=15; available:bool=True
class OrderIn(BaseModel): items:list[dict]; customer_note:str=''; address:str=''; payment_method:str=''
class StockIn(BaseModel): name:str;category:str='';quantity:float=0;minimum:float=0;expiry:str=''
class EmployeeIn(BaseModel): name:str;role:str='Atendente';phone:str='';shift:str='Integral';hire_date:str='';status:str='Ativo'
class PaymentIn(BaseModel): order_id:int|None=None;customer:str='';amount:float=Field(ge=0);method:str='PIX';status:str='Pago'
class ExpenseIn(BaseModel): description:str;amount:float=Field(ge=0)
def user_from(token):
 with db() as c:r=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?',(token,now())).fetchone()
 if not r:raise HTTPException(401,'Sessão inválida ou expirada')
 return dict(r)
def auth(authorization:str=Header(default='')):
 if not authorization.startswith('Bearer '):raise HTTPException(401,'Faça login para continuar')
 return user_from(authorization[7:])
def role(*roles):
 def dep(u=Depends(auth)):
  if u['role'] not in roles:raise HTTPException(403,'Sem permissão')
  if u['status']!='Ativo':raise HTTPException(403,'Conta inativa')
  return u
 return dep
def tenant(u):
 if u['role']!='restaurant' or not u['restaurant_id']:raise HTTPException(403,'Área exclusiva de restaurante')
 with db() as c:r=c.execute('SELECT * FROM restaurants WHERE id=? AND status="Aprovado"',(u['restaurant_id'],)).fetchone()
 if not r:raise HTTPException(403,'Restaurante pendente ou suspenso')
 return dict(r)
def query(sql,p=()):
 with db() as c:return [dict(x) for x in c.execute(sql,p).fetchall()]
def session(uid):
 t=secrets.token_urlsafe(36)
 with db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(t,uid,(datetime.now()+timedelta(days=7)).isoformat(timespec='seconds')))
 return t
@app.get('/api/health')
def health():return {'status':'ok','app':'MenuFlow'}
@app.post('/api/register/client')
def register_client(p:Register):
 try:
  with db() as c:c.execute('INSERT INTO users(name,email,phone,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?,?)',(p.name,p.email.lower().strip(),p.phone,pw_hash(p.password),'client','Ativo',now()))
 except sqlite3.IntegrityError:raise HTTPException(409,'E-mail já cadastrado')
 return {'ok':True}
@app.post('/api/register/restaurant')
def register_rest(p:RestaurantRequest):
 try:
  with db() as c:
   cur=c.execute('INSERT INTO restaurants(name,owner,email,phone,address,status,created_at) VALUES(?,?,?,?,?,?,?)',(p.name,p.owner,p.email.lower().strip(),p.phone,p.address,'Pendente',now()));rid=cur.lastrowid
   c.execute('INSERT INTO users(name,email,phone,password_hash,role,restaurant_id,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(p.owner,p.email.lower().strip(),p.phone,pw_hash(p.password),'restaurant',rid,'Ativo',now()))
 except sqlite3.IntegrityError:raise HTTPException(409,'E-mail já cadastrado')
 return {'ok':True,'status':'Pendente'}
@app.post('/api/login')
def login(p:Login):
 with db() as c:r=c.execute('SELECT * FROM users WHERE email=?',(p.email.lower().strip(),)).fetchone()
 if not r or not verify(p.password,r['password_hash']):raise HTTPException(401,'E-mail ou senha inválidos')
 if r['status']!='Ativo':raise HTTPException(403,'Conta suspensa')
 if r['role']=='restaurant':
  with db() as c:rs=c.execute('SELECT status FROM restaurants WHERE id=?',(r['restaurant_id'],)).fetchone()
  if not rs or rs['status']!='Aprovado':raise HTTPException(403,'Cadastro aguardando aprovação do suporte')
 return {'token':session(r['id']),'role':r['role'],'name':r['name'],'restaurant_id':r['restaurant_id']}
@app.post('/api/logout')
def logout(u=Depends(auth),authorization:str=Header(default='')):
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(authorization[7:],))
 return {'ok':True}
# Client marketplace
@app.get('/api/client/restaurants')
def client_restaurants(u=Depends(role('client'))):return query('SELECT id,name,address FROM restaurants WHERE status="Aprovado" ORDER BY name')
@app.get('/api/client/restaurants/{rid}/products')
def client_products(rid:int,u=Depends(role('client'))):
 with db() as c:
  if not c.execute('SELECT id FROM restaurants WHERE id=? AND status="Aprovado"',(rid,)).fetchone():raise HTTPException(404,'Restaurante indisponível')
  return [dict(x) for x in c.execute('SELECT id,name,category,price,description,ingredients,prep_minutes FROM products WHERE restaurant_id=? AND available=1 ORDER BY category,name',(rid,))]
@app.post('/api/client/restaurants/{rid}/orders')
def create_order(rid:int,p:OrderIn,u=Depends(role('client'))):
 if not p.items:raise HTTPException(400,'Selecione produtos')
 with db() as c:
  if not c.execute('SELECT id FROM restaurants WHERE id=? AND status="Aprovado"',(rid,)).fetchone():raise HTTPException(404,'Restaurante indisponível')
  parts=[];total=0
  for item in p.items:
   prod=c.execute('SELECT id,name,price FROM products WHERE id=? AND restaurant_id=? AND available=1',(item.get('product_id'),rid)).fetchone();qty=int(item.get('quantity',0))
   if not prod or qty<1 or qty>50:raise HTTPException(400,'Produto/quantidade inválida')
   total+=prod['price']*qty;parts.append({'name':prod['name'],'quantity':qty,'unit_price':prod['price'],'extras':str(item.get('extras','')),'remove':str(item.get('remove',''))})
  cur=c.execute('INSERT INTO orders(restaurant_id,customer_id,customer,items_json,total,status,created_at) VALUES(?,?,?,?,?,?,?)',(rid,u['id'],u['name'],json.dumps({'items':parts,'note':p.customer_note,'address':p.address,'payment':p.payment_method},ensure_ascii=False),total,'Aguardando',now()))
 return {'ok':True,'order_id':cur.lastrowid,'total':total}
@app.get('/api/client/orders')
def client_orders(u=Depends(role('client'))):
 x=query('SELECT id,restaurant_id,total,status,created_at,items_json FROM orders WHERE customer_id=? ORDER BY id DESC',(u['id'],))
 for o in x:
  o['restaurant_name']=(query('SELECT name FROM restaurants WHERE id=?',(o['restaurant_id'],)) or [{}])[0].get('name','Restaurante')
 return x
# Platform support
@app.get('/api/support/restaurants')
def support_restaurants(u=Depends(role('support'))):return query('SELECT * FROM restaurants ORDER BY id DESC')
@app.patch('/api/support/restaurants/{rid}')
def support_status(rid:int,p:dict,u=Depends(role('support'))):
 st=p.get('status')
 if st not in ['Pendente','Aprovado','Suspenso']:raise HTTPException(400,'Status inválido')
 with db() as c:c.execute('UPDATE restaurants SET status=? WHERE id=?',(st,rid))
 return {'ok':True}
@app.get('/api/support/users')
def support_users(u=Depends(role('support'))):return query('SELECT id,name,email,role,status,created_at FROM users ORDER BY id DESC')
# Restaurant modules, strictly scoped
@app.get('/api/restaurant/products')
def restaurant_products(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM products WHERE restaurant_id=? ORDER BY category,name',(r['id'],))
@app.post('/api/restaurant/products')
def restaurant_product_add(p:ProductIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('INSERT INTO products(restaurant_id,name,category,price,description,ingredients,prep_minutes,available) VALUES(?,?,?,?,?,?,?,?)',(r['id'],p.name,p.category,p.price,p.description,p.ingredients,p.prep_minutes,int(p.available)))
 return {'id':cur.lastrowid,'ok':True}
@app.put('/api/restaurant/products/{pid}')
def restaurant_product_edit(pid:int,p:ProductIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('UPDATE products SET name=?,category=?,price=?,description=?,ingredients=?,prep_minutes=?,available=? WHERE id=? AND restaurant_id=?',(p.name,p.category,p.price,p.description,p.ingredients,p.prep_minutes,int(p.available),pid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Produto não encontrado')
 return {'ok':True}
@app.delete('/api/restaurant/products/{pid}')
def restaurant_product_del(pid:int,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('DELETE FROM products WHERE id=? AND restaurant_id=?',(pid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Produto não encontrado')
 return {'ok':True}
@app.get('/api/restaurant/orders')
def restaurant_orders(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM orders WHERE restaurant_id=? ORDER BY id DESC',(r['id'],))
@app.patch('/api/restaurant/orders/{oid}')
def restaurant_order_status(oid:int,p:dict,u=Depends(role('restaurant'))):
 r=tenant(u);st=p.get('status')
 if st not in ['Aguardando','Em preparo','Pronto','Saiu para entrega','Concluído','Cancelado']:raise HTTPException(400,'Status inválido')
 with db() as c:cur=c.execute('UPDATE orders SET status=? WHERE id=? AND restaurant_id=?',(st,oid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Pedido não encontrado')
 return {'ok':True}
@app.get('/api/restaurant/stock')
def stock_list(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM stock WHERE restaurant_id=? ORDER BY name',(r['id'],))
@app.post('/api/restaurant/stock')
def stock_add(p:StockIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('INSERT INTO stock(restaurant_id,name,category,quantity,minimum,expiry) VALUES(?,?,?,?,?,?)',(r['id'],p.name,p.category,p.quantity,p.minimum,p.expiry))
 return {'id':cur.lastrowid,'ok':True}
@app.put('/api/restaurant/stock/{sid}')
def stock_edit(sid:int,p:StockIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('UPDATE stock SET name=?,category=?,quantity=?,minimum=?,expiry=? WHERE id=? AND restaurant_id=?',(p.name,p.category,p.quantity,p.minimum,p.expiry,sid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Item não encontrado')
 return {'ok':True}
@app.post('/api/restaurant/stock/{sid}/movement')
def stock_move(sid:int,p:dict,u=Depends(role('restaurant'))):
 r=tenant(u);kind=p.get('kind');qty=float(p.get('quantity',0));note=str(p.get('note',''))
 if kind not in ('Entrada','Saída') or qty<=0:raise HTTPException(400,'Movimentação inválida')
 with db() as c:
  item=c.execute('SELECT * FROM stock WHERE id=? AND restaurant_id=?',(sid,r['id'])).fetchone()
  if not item:raise HTTPException(404,'Item não encontrado')
  newqty=item['quantity']+qty if kind=='Entrada' else item['quantity']-qty
  if newqty<0:raise HTTPException(400,'Estoque insuficiente')
  c.execute('UPDATE stock SET quantity=? WHERE id=? AND restaurant_id=?',(newqty,sid,r['id']))
  c.execute('INSERT INTO stock_movements(restaurant_id,stock_id,kind,quantity,note,created_at) VALUES(?,?,?,?,?,?)',(r['id'],sid,kind,qty,note,now()))
 return {'ok':True}
@app.get('/api/restaurant/stock/movements')
def stock_history(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM stock_movements WHERE restaurant_id=? ORDER BY id DESC',(r['id'],))
@app.get('/api/restaurant/employees')
def employee_list(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM employees WHERE restaurant_id=? ORDER BY name',(r['id'],))
@app.post('/api/restaurant/employees')
def employee_add(p:EmployeeIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('INSERT INTO employees(restaurant_id,name,role,phone,shift,hire_date,status) VALUES(?,?,?,?,?,?,?)',(r['id'],p.name,p.role,p.phone,p.shift,p.hire_date,p.status))
 return {'id':cur.lastrowid,'ok':True}
@app.put('/api/restaurant/employees/{eid}')
def employee_edit(eid:int,p:EmployeeIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('UPDATE employees SET name=?,role=?,phone=?,shift=?,hire_date=?,status=? WHERE id=? AND restaurant_id=?',(p.name,p.role,p.phone,p.shift,p.hire_date,p.status,eid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Funcionário não encontrado')
 return {'ok':True}
@app.delete('/api/restaurant/employees/{eid}')
def employee_del(eid:int,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('DELETE FROM employees WHERE id=? AND restaurant_id=?',(eid,r['id']))
 if not cur.rowcount:raise HTTPException(404,'Funcionário não encontrado')
 return {'ok':True}
@app.get('/api/restaurant/payments')
def payment_list(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM payments WHERE restaurant_id=? ORDER BY id DESC',(r['id'],))
@app.post('/api/restaurant/payments')
def payment_add(p:PaymentIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('INSERT INTO payments(restaurant_id,order_id,customer,amount,method,status,created_at) VALUES(?,?,?,?,?,?,?)',(r['id'],p.order_id,p.customer,p.amount,p.method,p.status,now()))
 return {'id':cur.lastrowid,'ok':True}
@app.get('/api/restaurant/expenses')
def expense_list(u=Depends(role('restaurant'))):r=tenant(u);return query('SELECT * FROM expenses WHERE restaurant_id=? ORDER BY id DESC',(r['id'],))
@app.post('/api/restaurant/expenses')
def expense_add(p:ExpenseIn,u=Depends(role('restaurant'))):
 r=tenant(u)
 with db() as c:cur=c.execute('INSERT INTO expenses(restaurant_id,description,amount,created_at) VALUES(?,?,?,?)',(r['id'],p.description,p.amount,now()))
 return {'id':cur.lastrowid,'ok':True}
@app.get('/api/restaurant/reports')
def reports(u=Depends(role('restaurant'))):
 r=tenant(u);orders=query('SELECT total,status,created_at FROM orders WHERE restaurant_id=?',(r['id'],));payments=query('SELECT amount,status FROM payments WHERE restaurant_id=?',(r['id'],));expenses=query('SELECT amount FROM expenses WHERE restaurant_id=?',(r['id'],));
 return {'orders':len(orders),'open_orders':sum(o['status'] not in ('Concluído','Cancelado') for o in orders),'sales':sum(p['amount'] for p in payments if p['status']=='Pago'),'order_revenue':sum(o['total'] for o in orders if o['status']=='Concluído'),'expenses':sum(e['amount'] for e in expenses),'low_stock':len(query('SELECT id FROM stock WHERE restaurant_id=? AND quantity<=minimum',(r['id'],)))}
app.mount('/',StaticFiles(directory=ROOT/'frontend',html=True),name='frontend')
