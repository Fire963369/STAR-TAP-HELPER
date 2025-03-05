from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///startup_ideas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Модели базы данных
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    ideas = db.relationship('Idea', backref='author', lazy=True)
    votes = db.relationship('Vote', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)


class Idea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    votes = db.relationship('Vote', backref='idea', lazy=True)
    comments = db.relationship('Comment', backref='idea', lazy=True)

    @property
    def vote_count(self):
        return sum(vote.value for vote in self.votes)


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)  # 1 - позитивный, -1 - негативный
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    idea_id = db.Column(db.Integer, db.ForeignKey('idea.id'), nullable=False)
    date_voted = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'idea_id', name='user_idea_uc'),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    idea_id = db.Column(db.Integer, db.ForeignKey('idea.id'), nullable=False)


# Маршруты
@app.route('/')
def home():
    ideas = Idea.query.order_by(Idea.date_posted.desc()).all()
    return render_template('home.html', ideas=ideas)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Проверка существования пользователя
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()

        if user_exists:
            flash('Имя пользователя уже занято. Выберите другое.')
            return redirect(url_for('register'))

        if email_exists:
            flash('Email уже зарегистрирован. Используйте другой или войдите.')
            return redirect(url_for('register'))

        # Создание нового пользователя
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )

        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация успешна! Пожалуйста, войдите.')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Добро пожаловать, {username}!')
            return redirect(url_for('home'))
        else:
            flash('Неудачный вход. Проверьте имя пользователя и пароль.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Вы вышли из системы.')
    return redirect(url_for('home'))


@app.route('/submit_idea', methods=['GET', 'POST'])
def submit_idea():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите чтобы добавить идею.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']

        new_idea = Idea(
            title=title,
            description=description,
            user_id=session['user_id']
        )

        db.session.add(new_idea)
        db.session.commit()

        flash('Ваша идея добавлена!')
        return redirect(url_for('home'))

    return render_template('submit_idea.html')


@app.route('/idea/<int:idea_id>')
def idea_detail(idea_id):
    idea = Idea.query.get_or_404(idea_id)
    return render_template('idea_detail.html', idea=idea)


@app.route('/vote/<int:idea_id>/<int:value>')
def vote(idea_id, value):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите чтобы голосовать.')
        return redirect(url_for('login'))

    # Проверка существующего голоса
    existing_vote = Vote.query.filter_by(
        user_id=session['user_id'],
        idea_id=idea_id
    ).first()

    if existing_vote:
        # Обновление существующего голоса
        existing_vote.value = value
        db.session.commit()
        flash('Ваш голос обновлен.')
    else:
        # Создание нового голоса
        new_vote = Vote(
            value=value,
            user_id=session['user_id'],
            idea_id=idea_id
        )
        db.session.add(new_vote)
        db.session.commit()
        flash('Ваш голос учтен.')

    return redirect(url_for('idea_detail', idea_id=idea_id))


@app.route('/comment/<int:idea_id>', methods=['POST'])
def add_comment(idea_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите чтобы комментировать.')
        return redirect(url_for('login'))

    content = request.form['content']

    if content:
        new_comment = Comment(
            content=content,
            user_id=session['user_id'],
            idea_id=idea_id
        )

        db.session.add(new_comment)
        db.session.commit()
        flash('Ваш комментарий добавлен.')

    return redirect(url_for('idea_detail', idea_id=idea_id))


@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите чтобы удалить комментарий.')
        return redirect(url_for('login'))

    comment = Comment.query.get_or_404(comment_id)

    # Проверка, что текущий пользователь является автором комментария
    if comment.user_id != session['user_id']:
        flash('Вы не можете удалить этот комментарий.')
        return redirect(url_for('idea_detail', idea_id=comment.idea_id))

    db.session.delete(comment)
    db.session.commit()

    flash('Комментарий успешно удален.')
    return redirect(url_for('idea_detail', idea_id=comment.idea_id))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=5000)
