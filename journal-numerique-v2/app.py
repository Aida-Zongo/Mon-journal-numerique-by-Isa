from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

# Configuration de l'application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_cle_secrete_ici_changez_la'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///journal_numerique.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Initialisation des extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'

# Configuration des types de fichiers autorisés
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Modèles de base de données
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Relation avec les articles
    articles = db.relationship('Article', backref='author', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def __repr__(self):
        return f'<User {self.username}>'

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_text = db.Column(db.Text)
    content_image_path = db.Column(db.String(255))
    content_video_path = db.Column(db.String(255))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def approve(self):
        self.status = 'approved'
        self.updated_at = datetime.utcnow()
    
    def reject(self):
        self.status = 'rejected'
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        return f'<Article {self.title}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes principales
@app.route('/')
def home():
    # Récupérer les articles approuvés pour la page d'accueil
    articles = Article.query.filter_by(status='approved').order_by(Article.created_at.desc()).limit(6).all()
    return render_template('home.html', articles=articles)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Connexion réussie!', 'success')
            
            # Redirection selon le rôle
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Email ou mot de passe incorrect.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Vérifier si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur existe déjà.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'error')
            return render_template('register.html')
        
        # Créer le nouvel utilisateur
        user = User(username=username, email=email)
        user.set_password(password)
        
        # Détection automatique de l'admin
        if email == 'aida04zng@gmail.com':
            user.role = 'admin'
        
        db.session.add(user)
        db.session.commit()
        
        flash('Inscription réussie! Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Tableau de bord utilisateur avec ses articles
    user_articles = Article.query.filter_by(author_id=current_user.id).order_by(Article.created_at.desc()).all()
    return render_template('dashboard.html', articles=user_articles)

@app.route('/articles')
def articles():
    # Page listant tous les articles approuvés
    approved_articles = Article.query.filter_by(status='approved').order_by(Article.created_at.desc()).all()
    return render_template('articles.html', articles=approved_articles)

@app.route('/article/<int:id>')
def article_detail(id):
    article = Article.query.get_or_404(id)
    
    # Vérifier si l'article est visible pour l'utilisateur
    if article.status != 'approved':
        if not current_user.is_authenticated or (current_user.id != article.author_id and not current_user.is_admin()):
            flash('Article non trouvé.', 'error')
            return redirect(url_for('articles'))
    
    return render_template('article_detail.html', article=article)

@app.route('/create_article', methods=['GET', 'POST'])
@login_required
def create_article():
    if request.method == 'POST':
        title = request.form['title']
        content_text = request.form.get('content_text', '')
        
        if not title:
            flash('Le titre est obligatoire.', 'error')
            return render_template('create_article.html')
        
        # Créer l'article
        article = Article(title=title, content_text=content_text, author_id=current_user.id)
        
        # Gérer l'upload d'image
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
                filename = secure_filename(file.filename)
                timestamp = str(int(datetime.now().timestamp()))
                filename = f"{timestamp}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'images', filename)
                file.save(filepath)
                article.content_image_path = f"uploads/images/{filename}"
        
        # Gérer l'upload de vidéo
        if 'video' in request.files:
            file = request.files['video']
            if file and file.filename and allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
                filename = secure_filename(file.filename)
                timestamp = str(int(datetime.now().timestamp()))
                filename = f"{timestamp}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', filename)
                file.save(filepath)
                article.content_video_path = f"uploads/videos/{filename}"
        
        db.session.add(article)
        db.session.commit()
        
        flash('Article créé avec succès! Il est en attente de modération.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('create_article.html')

@app.route('/edit_article/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_article(id):
    article = Article.query.get_or_404(id)
    
    # Vérifier les permissions
    if article.author_id != current_user.id and not current_user.is_admin():
        flash('Vous n\'êtes pas autorisé à modifier cet article.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        article.title = request.form['title']
        article.content_text = request.form.get('content_text', '')
        
        # Remettre en attente si modifié par l'auteur (sauf si admin)
        if article.author_id == current_user.id and not current_user.is_admin():
            article.status = 'pending'
        
        article.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash('Article mis à jour avec succès.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('edit_article.html', article=article)

@app.route('/delete_article/<int:id>')
@login_required
def delete_article(id):
    article = Article.query.get_or_404(id)
    
    # Vérifier les permissions
    if article.author_id != current_user.id and not current_user.is_admin():
        flash('Vous n\'êtes pas autorisé à supprimer cet article.', 'error')
        return redirect(url_for('dashboard'))
    
    # Supprimer les fichiers associés
    if article.content_image_path:
        try:
            os.remove(os.path.join('static', article.content_image_path))
        except:
            pass
    
    if article.content_video_path:
        try:
            os.remove(os.path.join('static', article.content_video_path))
        except:
            pass
    
    db.session.delete(article)
    db.session.commit()
    
    flash('Article supprimé avec succès.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/moderator/approve/<int:id>')
@login_required
def moderator_approve_article(id):
    print(">> Tentative d'approbation de l'article ID:", id)
    print(">> Utilisateur connecté :", current_user.username)
    print(">> Rôle modérateur :", getattr(current_user, 'is_moderator', lambda: 'Non défini')())

    if not current_user.is_moderator():
        print(">> Refus : utilisateur sans droits de modération")
        flash('Accès refusé. Droits de modération requis.', 'error')
        return redirect(url_for('dashboard'))

    article = Article.query.get_or_404(id)

    print(">> Statut actuel de l'article :", article.status)

    if article.status != 'pending':
        print(">> Article déjà traité.")
        flash('Cet article n\'est pas en attente.', 'info')
        return redirect(url_for('dashboard'))

    article.approve()
    db.session.commit()

    print(f'>> Article approuvé : {article.title}')
    flash(f'L\'article "{article.title}" a été approuvé.', 'success')
    return redirect(url_for('dashboard'))



# Routes d'administration
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        flash('Accès refusé. Droits administrateur requis.', 'error')
        return redirect(url_for('home'))
    
    # Statistiques pour le tableau de bord admin
    pending_count = Article.query.filter_by(status='pending').count()
    approved_count = Article.query.filter_by(status='approved').count()
    rejected_count = Article.query.filter_by(status='rejected').count()
    total_users = User.query.count()
    
    stats = {
        'pending': pending_count,
        'approved': approved_count,
        'rejected': rejected_count,
        'total_users': total_users
    }
    
    return render_template('admin_dashboard.html', stats=stats)

@app.route('/admin/pending')
@login_required
def admin_pending():
    if not current_user.is_admin():
        flash('Accès refusé.', 'error')
        return redirect(url_for('home'))
    
    pending_articles = Article.query.filter_by(status='pending').order_by(Article.created_at.desc()).all()
    return render_template('admin_pending.html', articles=pending_articles)

@app.route('/admin/approve/<int:id>')
@login_required
def approve_article(id):
    if not current_user.is_admin():
        flash('Accès refusé.', 'error')
        return redirect(url_for('home'))
    
    article = Article.query.get_or_404(id)
    article.approve()
    db.session.commit()
    
    flash(f'Article "{article.title}" approuvé avec succès.', 'success')
    return redirect(url_for('admin_pending'))

@app.route('/admin/reject/<int:id>')
@login_required
def reject_article(id):
    if not current_user.is_admin():
        flash('Accès refusé.', 'error')
        return redirect(url_for('home'))
    
    article = Article.query.get_or_404(id)
    article.reject()
    db.session.commit()
    
    flash(f'Article "{article.title}" rejeté.', 'info')
    return redirect(url_for('admin_pending'))

@app.route('/admin/all_articles')
@login_required
def admin_all_articles():
    if not current_user.is_admin():
        flash('Accès refusé.', 'error')
        return redirect(url_for('home'))
    
    status_filter = request.args.get('status', '')
    if status_filter:
        articles = Article.query.filter_by(status=status_filter).order_by(Article.created_at.desc()).all()
    else:
        articles = Article.query.order_by(Article.created_at.desc()).all()
    
    return render_template('admin_all_articles.html', articles=articles, current_filter=status_filter)

# Route pour afficher la liste des membres (page admin)
@app.route('/admin/members')
@login_required
def admin_members():
    if not current_user.is_admin():
        flash('Accès refusé. Droits administrateur requis.', 'error')
        return redirect(url_for('home'))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_members.html', users=users)





# Initialisation de la base de données
def init_db():
    with app.app_context():
        db.create_all()
        print("Base de données initialisée!")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5002, debug=True)

