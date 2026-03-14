# Lost & Found Campus System
# Requirements: Flask, Pillow, imagehash

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import uuid
import imagehash
from PIL import Image
from datetime import datetime

# Create necessary directories
os.makedirs('static/uploads', exist_ok=True)

# Use /tmp for Render
db_path = '/tmp/lost_found.db' if os.path.exists('/tmp') else 'lost_found.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'campus-lost-found-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items_reported = db.relationship('Item', backref='reporter', lazy=True)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    item_type = db.Column(db.String(100))
    location = db.Column(db.String(200))
    campus_area = db.Column(db.String(100))
    image_hash = db.Column(db.String(100))
    image_path = db.Column(db.String(300))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    found_matches = db.relationship('Match', foreign_keys='Match.found_item_id', backref='found_item', lazy=True)
    lost_matches = db.relationship('Match', foreign_keys='Match.lost_item_id', backref='lost_item', lazy=True)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    found_item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    lost_item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    similarity = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def get_image_hash(image_path):
    try:
        img = Image.open(image_path)
        hash_val = imagehash.phash(img)
        return str(hash_val)
    except:
        return None

def calculate_similarity(hash1, hash2):
    if not hash1 or not hash2:
        return 0
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        similarity = 1 - (h1 - h2) / len(h1) * len(h2)
        return max(0, similarity * 100)
    except:
        return 0

def find_matches(item_id, item_hash):
    if not item_hash:
        return []
    all_items = Item.query.filter(Item.id != item_id, Item.status != 'resolved').all()
    matches = []
    for item in all_items:
        if item.category == item.category:
            similarity = calculate_similarity(item_hash, item.image_hash)
            if similarity > 60:
                matches.append({'item': item, 'similarity': similarity})
    return sorted(matches, key=lambda x: x['similarity'], reverse=True)[:5]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        phone = request.form.get('phone')
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))
        new_user = User(email=email, name=name, phone=phone)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            return redirect(url_for('dashboard', user_id=user.id))
        flash('User not found. Please register first.', 'error')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('login'))
    my_items = Item.query.filter_by(user_id=user_id).order_by(Item.created_at.desc()).all()
    lost_items = Item.query.filter_by(category='lost', status='pending').order_by(Item.created_at.desc()).limit(10).all()
    found_items = Item.query.filter_by(category='found', status='pending').order_by(Item.created_at.desc()).limit(10).all()
    return render_template('dashboard.html', user=user, my_items=my_items, lost_items=lost_items, found_items=found_items)

@app.route('/report', methods=['GET', 'POST'])
def report_item():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        item_type = request.form.get('item_type')
        location = request.form.get('location')
        campus_area = request.form.get('campus_area')
        image_path = None
        image_hash = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(str(uuid.uuid4()) + '_' + file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_path = filename
                image_hash = get_image_hash(filepath)
        new_item = Item(title=title, description=description, category=category, item_type=item_type, location=location, campus_area=campus_area, image_path=image_path, image_hash=image_hash, user_id=user_id)
        db.session.add(new_item)
        db.session.commit()
        if image_hash:
            matches = find_matches(new_item.id, image_hash)
            for match in matches:
                new_match = Match(found_item_id=match['item'].id if match['item'].category == 'found' else new_item.id, lost_item_id=new_item.id if match['item'].category == 'found' else match['item'].id, similarity=match['similarity'])
                db.session.add(new_match)
            db.session.commit()
        flash(f'{category.title()} item reported successfully!', 'success')
        return redirect(url_for('dashboard', user_id=user_id))
    return render_template('report.html', user=user)

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    item = Item.query.get(item_id)
    user_id = request.args.get('user_id')
    user = User.query.get(user_id) if user_id else None
    matches = Match.query.filter((Match.found_item_id == item_id) | (Match.lost_item_id == item_id)).all()
    return render_template('item_detail.html', item=item, matches=matches, user=user)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', 'all')
    items = Item.query.filter(Item.status != 'resolved')
    if query:
        items = items.filter((Item.title.contains(query)) | (Item.description.contains(query)))
    if category != 'all':
        items = items.filter_by(category=category)
    items = items.order_by(Item.created_at.desc()).limit(20).all()
    return render_template('search.html', items=items, query=query, category=category)

@app.route('/api/items')
def api_items():
    category = request.args.get('category', 'all')
    items = Item.query.filter(Item.status != 'resolved')
    if category != 'all':
        items = items.filter_by(category=category)
    items = items.order_by(Item.created_at.desc()).limit(50).all()
    return jsonify([{'id': item.id, 'title': item.title, 'category': item.category, 'item_type': item.item_type, 'location': item.location, 'campus_area': item.campus_area, 'image': url_for('static', filename='uploads/' + item.image_path) if item.image_path else None, 'created_at': item.created_at.isoformat()} for item in items])

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
