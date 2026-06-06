from flask import Flask, render_template, request, redirect, session, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)

@app.route('/')
def index():
    return redirect('/menu')

app.secret_key = "estoque_super_secreto_2026"

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://automatico:yC0t7wVgQ2ozXUMfhtdUT8l4FZue9HW3@dpg-d8fpjbv7f7vs73ejl8sg-a.oregon-postgres.render.com/estoque_zd9a"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================
# PRODUTOS
# ==========================
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50))
    nome = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    validade = db.Column(db.String(20))
    endereco = db.Column(db.String(20), unique=True, nullable=False)

# ==========================
# HISTÓRICO
# ==========================
class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(30))
    usuario = db.Column(db.String(100))
    acao = db.Column(db.String(50))
    produto = db.Column(db.String(200))
    quantidade = db.Column(db.Integer)
    origem = db.Column(db.String(255))
    destino = db.Column(db.String(255))

# ==========================
# USUÁRIOS
# ==========================
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)

# ==========================
# FUNÇÕES
# ==========================
def logado():
    return session.get('usuario')

def admin():
    return session.get('perfil') == 'admin'

def operador_ou_admin_ou_separacao():
    return session.get('perfil') in ['admin', 'operador', 'separacao']

def operador_ou_admin():
    return session.get('perfil') in ['admin', 'operador']

# ==========================
# MOVIMENTAÇÃO
# ==========================
@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    busca = request.args.get("busca", "")
    produtos = Produto.query.all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in (p.nome or "").lower()
            or busca.lower() in (p.codigo or "").lower()
            or busca.lower() in (p.endereco or "").lower()
        ]

    if request.method == 'POST':

        produto_id = request.form['produto_id']
        acao = request.form['acao']
        quantidade = int(request.form['quantidade'])

        usuario = session.get('usuario')

        produto = Produto.query.get(produto_id)

        if not produto:
            return redirect('/movimentacao')

        # ==========================
        # ENTRADA
        # ==========================
        if acao == "entrada":

            produto.quantidade += quantidade

            historico = Historico(
                data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
                usuario=usuario,
                acao="ENTRADA",
                produto=produto.nome,
                quantidade=quantidade,
                origem=produto.endereco,
                destino=produto.endereco
            )

            db.session.add(historico)
            db.session.commit()

            return redirect('/movimentacao?sucesso=entrada')

        # ==========================
        # SAÍDA (IMPORTANTE PRO RANKING)
        # ==========================
        if acao == "saida":

            produto.quantidade -= quantidade

            historico = Historico(
                data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
                usuario=usuario,
                acao="SAIDA",
                produto=produto.nome,
                quantidade=quantidade,
                origem=produto.endereco,
                destino="-"
            )

            db.session.add(historico)

            if produto.quantidade <= 0:
                db.session.delete(produto)
                db.session.commit()
                return redirect('/movimentacao?sucesso=zerado')

            db.session.commit()

            return redirect('/movimentacao?sucesso=saida')

    return render_template(
        'movimentacao.html',
        produtos=produtos,
        busca=busca
    )

# ==========================
# 🏆 RANKING DE USUÁRIOS (NOVO)
# ==========================
@app.route('/ranking-usuarios')
def ranking_usuarios():

    if not operador_ou_admin():
        return redirect('/menu')

    dados = db.session.query(
        Historico.usuario,
        db.func.sum(Historico.quantidade).label('total')
    ).filter(
        Historico.acao == "SAIDA"
    ).group_by(
        Historico.usuario
    ).order_by(
        db.desc('total')
    ).all()

    return render_template('ranking.html', dados=dados)

# ==========================
# INIT
# ==========================
with app.app_context():
    db.create_all()

    admin_user = Usuario.query.filter_by(usuario='admin').first()

    if not admin_user:
        novo_admin = Usuario(
            usuario='admin',
            senha='10080810',
            perfil='admin'
        )

        db.session.add(novo_admin)
        db.session.commit()

if __name__ == '__main__':
    app.run()
