from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

app.secret_key = "estoque_super_secreto_2026"

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://automatico:yC0t7wVgQ2ozXUMfhtdUT8l4FZue9HW3@dpg-d8fpjbv7f7vs73ejl8sg-a.oregon-postgres.render.com/estoque_zd9a"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================
# MODELOS
# ==========================
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50))
    nome = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    validade = db.Column(db.String(20))
    endereco = db.Column(db.String(20), unique=True, nullable=False)


class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(30))
    usuario = db.Column(db.String(100))
    acao = db.Column(db.String(50))
    produto = db.Column(db.String(200))
    quantidade = db.Column(db.Integer)
    origem = db.Column(db.String(20))
    destino = db.Column(db.String(20))


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)


# ==========================
# PERMISSÕES
# ==========================
def logado():
    return session.get('usuario')


def pode_consultar():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


def pode_inventario():
    return session.get('perfil') in ['admin', 'operador']


def pode_cadastrar():
    return session.get('perfil') in ['admin', 'operador']


def pode_separar():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


# ==========================
# STATUS
# ==========================
def calcular_status(validade):
    try:
        hoje = datetime.today()
        data = datetime.strptime(validade, "%d/%m/%Y")

        meses = (data.year - hoje.year) * 12 + data.month - hoje.month

        if meses <= 4:
            return "URGENTE", 1
        elif meses <= 7:
            return "ATENÇÃO", 2
        else:
            return "OK", 3
    except:
        return "SEM_DATA", 4


# ==========================
# LOGIN
# ==========================
@app.route('/')
def login():
    if session.get('usuario'):
        return redirect('/menu')
    return render_template('login.html')


@app.route('/entrar', methods=['POST'])
def entrar():
    user = Usuario.query.filter_by(
        usuario=request.form['usuario'],
        senha=request.form['senha']
    ).first()

    if not user:
        return redirect('/')

    session['usuario'] = user.usuario
    session['perfil'] = user.perfil

    return redirect('/menu')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/menu')
def menu():
    if not logado():
        return redirect('/')

    return render_template(
        'menu.html',
        usuario=session.get('usuario'),
        perfil=session.get('perfil')
    )


# ==========================
# CADASTRO
# ==========================
@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():

    if not pode_cadastrar():
        return redirect('/menu')

    if request.method == 'POST':

        endereco = f"{request.form['rua']}-{request.form['coluna']}-{request.form['nivel']}"

        existe = Produto.query.filter_by(endereco=endereco).first()
        if existe:
            return redirect('/cadastrar?erro=endereco')

        produto = Produto(
            codigo=request.form['codigo'],
            nome=request.form['nome'],
            quantidade=int(request.form['quantidade']),
            validade=request.form['validade'],
            endereco=endereco
        )

        db.session.add(produto)

        db.session.add(Historico(
            data=datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CADASTRO",
            produto=produto.nome,
            quantidade=produto.quantidade,
            origem="-",
            destino=endereco
        ))

        db.session.commit()

        return redirect('/cadastrar?sucesso=1')

    return render_template('cadastrar.html')


# ==========================
# INVENTÁRIO
# ==========================
@app.route('/inventario')
def inventario():

    if not pode_inventario():
        return redirect('/menu')

    produtos = Produto.query.all()

    lista = []
    for p in produtos:
        status, prioridade = calcular_status(p.validade)
        lista.append({"produto": p, "status": status, "prioridade": prioridade})

    lista.sort(key=lambda x: x["prioridade"])

    return render_template('inventario.html', lista=lista)


# ==========================
# CONSULTA
# ==========================
@app.route('/consulta')
def consulta():

    if not pode_consultar():
        return redirect('/menu')

    busca = request.args.get('busca', '')
    produtos = Produto.query.all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
            or busca.lower() in p.endereco.lower()
        ]

    lista = []
    for p in produtos:
        status, prioridade = calcular_status(p.validade)
        lista.append({"produto": p, "status": status, "prioridade": prioridade})

    lista.sort(key=lambda x: x["prioridade"])

    return render_template('consulta.html', lista=lista, busca=busca)


# ==========================
# SEPARAÇÃO
# ==========================
@app.route('/separar', methods=['GET', 'POST'])
def separar():

    if not pode_separar():
        return redirect('/menu')

    produto = None
    endereco = ""
    mensagem = ""

    if request.method == 'POST':

        endereco = request.form['endereco']
        produto = Produto.query.filter_by(endereco=endereco).first()

        if produto:
            mensagem = "tem_produto"
        else:
            mensagem = "vazio"

    return render_template(
        'separar.html',
        produto=produto,
        endereco=endereco,
        mensagem=mensagem
    )


# ==========================
# MOVIMENTAÇÃO
# ==========================
@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():

    if session.get('perfil') not in ['admin', 'operador']:
        return redirect('/menu')

    produtos = Produto.query.all()

    if request.method == 'POST':

        produto = Produto.query.get(request.form['produto_id'])
        qtd = int(request.form['quantidade'])
        acao = request.form['acao']

        if acao == "entrada":
            produto.quantidade += qtd

        if acao == "saida":
            produto.quantidade -= qtd

        db.session.add(Historico(
            data=datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao=acao.upper(),
            produto=produto.nome,
            quantidade=qtd,
            origem=produto.endereco,
            destino=produto.endereco if acao == "entrada" else "-"
        ))

        db.session.commit()

        return redirect('/movimentacao')

    return render_template('movimentacao.html', produtos=produtos)


# ==========================
# RESTANTE SIMPLES
# ==========================
@app.route('/excluir/<int:id>')
def excluir(id):

    if not pode_inventario():
        return redirect('/menu')

    produto = Produto.query.get_or_404(id)

    db.session.delete(produto)
    db.session.commit()

    return redirect('/inventario')


# ==========================
# INIT
# ==========================
with app.app_context():
    db.create_all()

    admin_user = Usuario.query.filter_by(usuario='admin').first()

    if not admin_user:
        db.session.add(Usuario(
            usuario='admin',
            senha='10080810',
            perfil='admin'
        ))
        db.session.commit()


if __name__ == '__main__':
    app.run()
