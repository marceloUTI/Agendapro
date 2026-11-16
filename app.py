import os
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import BytesIO
from urllib.parse import quote

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-only-change-me')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')


def connection():
    config = {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', 'agendapro'),
        'charset': 'utf8mb4',
        'cursorclass': DictCursor,
        'autocommit': False
    }

    if os.getenv('MYSQL_SSL', 'false').lower() == 'true':
        config['ssl_ca'] = os.getenv('MYSQL_SSL_CA', 'ca.pem')
        config['ssl_verify_cert'] = True
        config['ssl_verify_identity'] = True

    return pymysql.connect(**config)

def query(sql, args=(), one=False):
    with connection() as db:
        with db.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone() if one else cur.fetchall()


def execute(sql, args=()):
    with connection() as db:
        with db.cursor() as cur:
            cur.execute(sql, args)
            rowid = cur.lastrowid
        db.commit()
        return rowid


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


def uid():
    return session['user_id']


def money(value):
    value = Decimal(str(value or 0))
    return 'R$ ' + f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

app.jinja_env.filters['brl'] = money


def decimal_field(name):
    try:
        value = Decimal(request.form[name].replace(',', '.'))
        if not value.is_finite() or value <= 0:
            raise ValueError
        return value
    except (InvalidOperation, ValueError, KeyError):
        raise ValueError('Informe um valor maior que zero.')


def own_client(client_id):
    item = query('SELECT * FROM clients WHERE id=%s AND user_id=%s', (client_id, uid()), one=True)
    if not item:
        abort(404)
    return item


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not name or not email or len(password) < 8:
            flash('Preencha nome e e-mail e use senha com pelo menos 8 caracteres.', 'error')
        elif query('SELECT id FROM users WHERE email=%s', (email,), one=True):
            flash('E-mail já cadastrado.', 'error')
        else:
            user_id = execute('INSERT INTO users (name,email,password_hash) VALUES (%s,%s,%s)',
                (name, email, generate_password_hash(password)))
            session.clear()
            session['user_id'], session['name'] = user_id, name
            return redirect(url_for('dashboard'))
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = query('SELECT * FROM users WHERE email=%s', (email,), one=True)
        if user and check_password_hash(user['password_hash'], request.form.get('password', '')):
            session.clear()
            session['user_id'], session['name'] = user['id'], user['name']
            return redirect(url_for('dashboard'))
        flash('E-mail ou senha inválidos.', 'error')
    return render_template('auth.html', mode='login')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    stats = query('''SELECT
      (SELECT COUNT(*) FROM appointments WHERE user_id=%s AND YEAR(scheduled_at)=YEAR(CURDATE()) AND MONTH(scheduled_at)=MONTH(CURDATE())) AS services,
      (SELECT COUNT(*) FROM appointments WHERE user_id=%s AND status IN ('Pendente','Confirmado')) AS appointments,
      (SELECT COALESCE(SUM(amount),0) FROM payments WHERE user_id=%s AND status='Recebido' AND YEAR(paid_at)=YEAR(CURDATE()) AND MONTH(paid_at)=MONTH(CURDATE())) AS received,
      (SELECT COALESCE(SUM(amount),0) FROM payments WHERE user_id=%s AND status='Pendente') AS pending''', (uid(),)*4, one=True)
    upcoming = query('''SELECT a.*,c.name AS client_name FROM appointments a JOIN clients c ON c.id=a.client_id
      WHERE a.user_id=%s AND a.scheduled_at>=NOW() AND a.status NOT IN ('Cancelado','Concluído') ORDER BY a.scheduled_at LIMIT 5''', (uid(),))
    return render_template('dashboard.html', page='dashboard', stats=stats, upcoming=upcoming)


@app.route('/clients')
@login_required
def clients():
    items = query('SELECT * FROM clients WHERE user_id=%s ORDER BY name', (uid(),))
    return render_template('clients.html', page='clients', items=items)


@app.route('/clients/new', methods=['POST'])
@login_required
def client_new():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Informe o nome do cliente.', 'error')
    else:
        execute('INSERT INTO clients (user_id,name,phone,email,address) VALUES (%s,%s,%s,%s,%s)',
            (uid(), name, request.form.get('phone','').strip(), request.form.get('email','').strip(), request.form.get('address','').strip()))
        flash('Cliente cadastrado.', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:item_id>/edit', methods=['POST'])
@login_required
def client_edit(item_id):
    own_client(item_id)
    name = request.form.get('name','').strip()
    if not name:
        flash('Informe o nome.', 'error')
    else:
        execute('UPDATE clients SET name=%s,phone=%s,email=%s,address=%s WHERE id=%s AND user_id=%s',
            (name,request.form.get('phone','').strip(),request.form.get('email','').strip(),request.form.get('address','').strip(),item_id,uid()))
        flash('Cliente atualizado.', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:item_id>/delete', methods=['POST'])
@login_required
def client_delete(item_id):
    own_client(item_id)
    execute('DELETE FROM clients WHERE id=%s AND user_id=%s', (item_id,uid()))
    flash('Cliente excluído. Seus agendamentos, orçamentos e pagamentos também foram excluídos.', 'success')
    return redirect(url_for('clients'))


@app.route('/appointments')
@login_required
def appointments():
    items = query('''SELECT a.*,c.name AS client_name FROM appointments a JOIN clients c ON c.id=a.client_id
        WHERE a.user_id=%s ORDER BY a.scheduled_at''', (uid(),))
    people = query('SELECT id,name FROM clients WHERE user_id=%s ORDER BY name', (uid(),))
    return render_template('appointments.html', page='appointments', items=items, people=people)


@app.route('/appointments/new', methods=['POST'])
@login_required
def appointment_new():
    try:
        client_id = int(request.form['client_id'])
        own_client(client_id)
        dt = datetime.fromisoformat(request.form['scheduled_at'])
        service = request.form.get('service','').strip()
        if not service:
            raise ValueError
        execute('INSERT INTO appointments (user_id,client_id,service,scheduled_at,notes) VALUES (%s,%s,%s,%s,%s)',
            (uid(),client_id,service,dt,request.form.get('notes','')))
        flash('Agendamento criado.', 'success')
    except (ValueError, KeyError):
        flash('Preencha cliente, serviço e data/hora válidos.', 'error')
    return redirect(url_for('appointments'))


@app.route('/appointments/<int:item_id>/status', methods=['POST'])
@login_required
def appointment_status(item_id):
    status = request.form.get('status')
    if status not in ('Pendente','Confirmado','Concluído','Cancelado'):
        abort(400)
    execute('UPDATE appointments SET status=%s WHERE id=%s AND user_id=%s', (status,item_id,uid()))
    return redirect(url_for('appointments'))


@app.route('/appointments/<int:item_id>/delete', methods=['POST'])
@login_required
def appointment_delete(item_id):
    execute('DELETE FROM appointments WHERE id=%s AND user_id=%s', (item_id,uid()))
    return redirect(url_for('appointments'))


@app.route('/estimates')
@login_required
def estimates():
    items = query('''SELECT e.*,c.name AS client_name,c.phone AS client_phone FROM estimates e JOIN clients c ON c.id=e.client_id
      WHERE e.user_id=%s ORDER BY e.created_at DESC''', (uid(),))
    people = query('SELECT id,name FROM clients WHERE user_id=%s ORDER BY name', (uid(),))
    return render_template('estimates.html', page='estimates', items=items, people=people)


@app.route('/estimates/new', methods=['POST'])
@login_required
def estimate_new():
    try:
        client_id = int(request.form['client_id'])
        own_client(client_id)
        amount = decimal_field('amount')
        service = request.form.get('service','').strip()
        if not service:
            raise ValueError
        execute('INSERT INTO estimates (user_id,client_id,service,description,amount) VALUES (%s,%s,%s,%s,%s)',
            (uid(),client_id,service,request.form.get('description',''),amount))
        flash('Orçamento criado.', 'success')
    except (ValueError, KeyError):
        flash('Preencha os campos do orçamento corretamente.', 'error')
    return redirect(url_for('estimates'))


@app.route('/estimates/<int:item_id>/status', methods=['POST'])
@login_required
def estimate_status(item_id):
    status = request.form.get('status')
    if status not in ('Pendente','Enviado','Aprovado','Recusado'):
        abort(400)
    execute('UPDATE estimates SET status=%s WHERE id=%s AND user_id=%s', (status,item_id,uid()))
    return redirect(url_for('estimates'))


@app.route('/estimates/<int:item_id>/delete', methods=['POST'])
@login_required
def estimate_delete(item_id):
    execute('DELETE FROM estimates WHERE id=%s AND user_id=%s', (item_id,uid()))
    return redirect(url_for('estimates'))


def own_estimate(item_id):
    item = query('''SELECT e.*,c.name AS client_name,c.phone AS client_phone FROM estimates e
       JOIN clients c ON c.id=e.client_id WHERE e.id=%s AND e.user_id=%s''', (item_id,uid()), one=True)
    if not item:
        abort(404)
    return item


@app.route('/estimates/<int:item_id>/pdf')
@login_required
def estimate_pdf(item_id):
    item = own_estimate(item_id)
    stream = BytesIO()
    pdf = Canvas(stream, pagesize=A4)
    width, height = A4
    pdf.setFillColor(colors.HexColor('#2563eb'))
    pdf.rect(0,height-110,width,110,fill=1,stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont('Helvetica-Bold',25)
    pdf.drawString(44,height-66,'AgendaPro')
    pdf.setFillColor(colors.HexColor('#111827'))
    pdf.setFont('Helvetica-Bold',17)
    pdf.drawString(44,height-155,f'Orcamento #{item_id:03d}')
    pdf.setFont('Helvetica',11)
    rows = [('Cliente',item['client_name']),('Servico',item['service']),('Valor',money(item['amount'])),
            ('Status',item['status']),('Emissao',item['created_at'].strftime('%d/%m/%Y'))]
    y=height-190
    for label,value in rows:
        pdf.setFont('Helvetica-Bold',10)
        pdf.drawString(44,y,label+':')
        pdf.setFont('Helvetica',10)
        # Helvetica's built-in encoding cannot render all unicode characters; replace unsupported characters.
        safe = str(value).encode('latin-1','replace').decode('latin-1')
        pdf.drawString(130,y,safe[:72])
        y-=29
    pdf.setFont('Helvetica-Bold',10)
    pdf.drawString(44,y-10,'Descricao:')
    from reportlab.lib.utils import simpleSplit
    lines = simpleSplit((item['description'] or 'Sem observacoes').encode('latin-1','replace').decode('latin-1'), 'Helvetica',10,width-88)
    pdf.setFont('Helvetica',10)
    for line in lines[:22]:
        y-=18
        pdf.drawString(44,y-18,line)
    pdf.setFont('Helvetica',9)
    pdf.drawString(44,45,'Gerado pelo AgendaPro')
    pdf.save()
    stream.seek(0)
    return send_file(stream,mimetype='application/pdf',as_attachment=True,download_name=f'orcamento-{item_id:03d}.pdf')


@app.route('/estimates/<int:item_id>/whatsapp')
@login_required
def estimate_whatsapp(item_id):
    item = own_estimate(item_id)
    message = f"Olá, {item['client_name']}! Segue o orçamento #{item_id:03d}: {item['service']} — {money(item['amount'])}."
    digits = ''.join(c for c in item['client_phone'] if c.isdigit())
    if digits and not digits.startswith('55'):
        digits = '55'+digits
    # WhatsApp pre-fills text only. The PDF must be attached manually after downloading.
    return redirect(f'https://wa.me/{digits}?text={quote(message)}')


@app.route('/finance')
@login_required
def finance():
    items = query('''SELECT p.*,c.name AS client_name FROM payments p JOIN clients c ON c.id=p.client_id
      WHERE p.user_id=%s ORDER BY p.paid_at DESC,p.id DESC''', (uid(),))
    stats = query('''SELECT
      COALESCE(SUM(CASE WHEN status='Recebido' AND YEAR(paid_at)=YEAR(CURDATE()) AND MONTH(paid_at)=MONTH(CURDATE()) THEN amount ELSE 0 END),0) received,
      COALESCE(SUM(CASE WHEN status='Pendente' THEN amount ELSE 0 END),0) pending,
      COUNT(CASE WHEN status='Recebido' AND YEAR(paid_at)=YEAR(CURDATE()) AND MONTH(paid_at)=MONTH(CURDATE()) THEN 1 END) paid_count
      FROM payments WHERE user_id=%s''', (uid(),), one=True)
    people = query('SELECT id,name FROM clients WHERE user_id=%s ORDER BY name', (uid(),))
    return render_template('finance.html', page='finance', items=items, stats=stats, people=people)


@app.route('/finance/new', methods=['POST'])
@login_required
def payment_new():
    try:
        client_id = int(request.form['client_id'])
        own_client(client_id)
        amount = decimal_field('amount')
        paid_at = date.fromisoformat(request.form['paid_at'])
        status = request.form['status']
        description = request.form.get('description','').strip()
        if not description or status not in ('Recebido','Pendente'):
            raise ValueError
        execute('INSERT INTO payments (user_id,client_id,description,amount,status,paid_at) VALUES (%s,%s,%s,%s,%s,%s)',
            (uid(),client_id,description,amount,status,paid_at))
        flash('Pagamento registrado.', 'success')
    except (ValueError, KeyError):
        flash('Preencha corretamente os dados do pagamento.', 'error')
    return redirect(url_for('finance'))


@app.route('/finance/<int:item_id>/status', methods=['POST'])
@login_required
def payment_status(item_id):
    status = request.form.get('status')
    if status not in ('Recebido','Pendente'):
        abort(400)
    execute('UPDATE payments SET status=%s WHERE id=%s AND user_id=%s',(status,item_id,uid()))
    return redirect(url_for('finance'))


@app.route('/finance/<int:item_id>/delete', methods=['POST'])
@login_required
def payment_delete(item_id):
    execute('DELETE FROM payments WHERE id=%s AND user_id=%s',(item_id,uid()))
    return redirect(url_for('finance'))


if __name__ == '__main__':
    app.run(debug=True)
