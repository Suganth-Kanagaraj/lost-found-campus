# Lost & Found Campus System
# Requirements: Flask, Pillow, imagehash, PostgreSQL

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

# Database configuration - supports both SQLite and PostgreSQL
# For PostgreSQL: Set DATABASE_URL environment variable
# For SQLite: Uses local file (default for local dev)
database_url = os.environ.get('DATABASE_URL')

# Initialize Flask app first
app = Flask(__name__)

if database_url:
    # Use PostgreSQL on Render
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Use SQLite for local development
    db_path = '/tmp/lost_found.db' if os.path.exists('/tmp') else 'lost_found.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SECRET_KEY'] = 'campus-lost-found-2026'
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
    """
    Enhanced image hashing using multiple algorithms for higher accuracy.
    Uses: pHash (perceptual), dHash (difference), wHash (wavelet), aHash (average)
    """
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize for consistent hashing
        img = img.resize((512, 512), Image.LANCZOS)
        
        # Generate multiple hash types
        phash = str(imagehash.phash(img))
        dhash = str(imagehash.dhash(img))
        whash = str(imagehash.whash(img))
        ahash = str(imagehash.average_hash(img))
        
        # Combine all hashes into one string
        combined_hash = f"{phash}|{dhash}|{whash}|{ahash}"
        return combined_hash
    except Exception as e:
        print(f"Error generating hash: {e}")
        return None

def calculate_similarity(hash1, hash2):
    """
    Enhanced similarity calculation using multiple hash comparison.
    Higher accuracy by comparing multiple hash types.
    """
    if not hash1 or not hash2:
        return 0
    
    try:
        # Split combined hashes
        hashes1 = hash1.split('|')
        hashes2 = hash2.split('|')
        
        if len(hashes1) < 4 or len(hashes2) < 4:
            # Fallback to simple comparison
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return max(0, (1 - (h1 - h2) / max(len(h1), len(h2)))) * 100
        
        total_similarity = 0
        weights = [0.4, 0.25, 0.2, 0.15]  # Weight pHash higher as it's most accurate
        
        for i, (h1_str, h2_str) in enumerate(zip(hashes1[:4], hashes2[:4])):
            try:
                h1 = imagehash.hex_to_hash(h1_str)
                h2 = imagehash.hex_to_hash(h2_str)
                # Calculate similarity for this hash type
                sim = (1 - (h1 - h2) / max(len(h1), len(h2)))
                total_similarity += sim * weights[i]
            except:
                continue
        
        return max(0, total_similarity * 100)
    except Exception as e:
        print(f"Error calculating similarity: {e}")
        return 0

def get_color_histogram(image_path, bins=32):
    """Extract color histogram for additional matching."""
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize for consistency
        img = img.resize((256, 256), Image.LANCZOS)
        
        # Get histogram for each channel
        r_hist = img.histogram()[0:256]
        g_hist = img.histogram()[256:512]
        b_hist = img.histogram()[512:768]
        
        # Simplify histogram (reduce bins)
        step = 256 // bins
        r_bins = [sum(r_hist[i*step:(i+1)*step]) for i in range(bins)]
        g_bins = [sum(g_hist[i*step:(i+1)*step]) for i in range(bins)]
        b_bins = [sum(b_hist[i*step:(i+1)*step]) for i in range(bins)]
        
        return r_bins + g_bins + b_bins
    except:
        return None

def color_histogram_similarity(hist1, hist2):
    """Compare two color histograms using correlation."""
    if not hist1 or not hist2 or len(hist1) != len(hist2):
        return 0
    
    try:
        # Simple correlation coefficient
        n = len(hist1)
        mean1 = sum(hist1) / n
        mean2 = sum(hist2) / n
        
        numerator = sum((h1 - mean1) * (h2 - mean2) for h1, h2 in zip(hist1, hist2))
        denom1 = sum((h - mean1) ** 2 for h in hist1) ** 0.5
        denom2 = sum((h - mean2) ** 2 for h in hist2) ** 0.5
        
        if denom1 * denom2 == 0:
            return 0
        
        correlation = numerator / (denom1 * denom2)
        return max(0, correlation * 100)
    except:
        return 0

def extract_dominant_colors(image_path, num_colors=5):
    """Extract dominant colors from an image using k-means clustering."""
    try:
        from PIL import Image
        import numpy as np
        
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize for faster processing
        img = img.resize((100, 100))
        img_array = np.array(img)
        
        # Reshape to list of pixels
        pixels = img_array.reshape(-1, 3)
        
        # Simple color quantization using averaging
        colors = {}
        for pixel in pixels:
            # Reduce color space by rounding
            key = tuple((np.array(pixel) // 32) * 32)
            colors[key] = colors.get(key, 0) + 1
        
        # Get top colors
        sorted_colors = sorted(colors.items(), key=lambda x: x[1], reverse=True)
        return [list(color[0]) for color in sorted_colors[:num_colors]]
    except Exception as e:
        print(f"Error extracting colors: {e}")
        return None

def color_similarity(colors1, colors2):
    """Calculate similarity between two color palettes."""
    if not colors1 or not colors2:
        return 0
    
    try:
        total_sim = 0
        for c1 in colors1[:3]:
            for c2 in colors2[:3]:
                # Euclidean distance
                dist = sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5
                # Convert distance to similarity (0-100)
                sim = max(0, 100 - dist)
                total_sim += sim
        
        return total_sim / 9  # Average
    except:
        return 0

def predict_category(title, description):
    """AI-powered category prediction based on text."""
    if not title:
        return None
    
    text = (title + " " + (description or "")).lower()
    
    # Keyword-based category prediction
    category_keywords = {
        'Electronics': ['phone', 'laptop', 'computer', 'charger', 'headphone', 'earphone', 'watch', 'camera', 'tablet', 'airpods', 'power bank', 'usb', 'cable', 'electronic'],
        'Books': ['book', 'notebook', 'notes', 'textbook', 'journal', 'dictionary', 'magazine', 'paper', 'assignment'],
        'Wallet': ['wallet', 'money', 'cash', 'card', 'credit', 'debit', 'id card', 'license'],
        'ID Card': ['id', 'card', 'student', 'badge', 'identity', 'pass', 'access'],
        'Clothing': ['shirt', 'pant', 'dress', 'jacket', 'hoodie', 'shoe', 'sandal', 'cap', 'hat', 'clothes', 'uniform'],
        'Keys': ['key', 'keychain', 'lock', '钥匙'],
        'Water Bottle': ['bottle', 'water', ' flask', 'cup', 'tumbler', 'thermos'],
        'Bag': ['bag', 'backpack', 'purse', 'wallet', 'pouch', 'bagpack'],
        'Accessories': ['spectacles', 'glasses', 'sunglasses', 'jewelry', 'watch', 'ring', 'chain', 'earring']
    }
    
    scores = {}
    for category, keywords in category_keywords.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score
    
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return 'Other'

def get_ai_suggestions(item_id, title, description, item_type, campus_area):
    """Get AI-powered suggestions for similar items."""
    suggestions = []
    
    # Find similar items
    all_items = Item.query.filter(
        Item.id != item_id,
        Item.status != 'resolved'
    ).all()
    
    for item in all_items:
        score = 0
        
        # Title similarity (30%)
        if title and item.title:
            title_sim = calculate_text_similarity(title, item.title)
            score += title_sim * 0.3
        
        # Description similarity (20%)
        if description and item.description:
            desc_sim = calculate_text_similarity(description, item.description)
            score += desc_sim * 0.2
        
        # Same category/type (25%)
        if item_type and item.item_type:
            if item_type.lower() == item.item_type.lower():
                score += 25
            elif item_type.lower() in item.item_type.lower() or item.item_type.lower() in item_type.lower():
                score += 15
        
        # Same campus area (15%)
        if campus_area and item.campus_area:
            if campus_area.lower() == item.campus_area.lower():
                score += 15
        
        # Time proximity (10%) - newer items more relevant
        if item.created_at:
            days_old = (datetime.utcnow() - item.created_at).days
            if days_old < 7:
                score += 10
            elif days_old < 30:
                score += 5
        
        if score > 30:
            suggestions.append({'item': item, 'score': round(score, 1)})
    
    return sorted(suggestions, key=lambda x: x['score'], reverse=True)[:5]

def calculate_text_similarity(text1, text2):
    """Simple text similarity based on common words."""
    if not text1 or not text2:
        return 0
    
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0
    
    intersection = words1 & words2
    union = words1 | words2
    
    return (len(intersection) / len(union)) * 100

def find_matches(item_id, item_hash, item_description="", item_type=""):
    """
    Enhanced matching using multiple algorithms:
    1. Multi-hash image similarity (50% weight)
    2. Text similarity (30% weight)
    3. Item type similarity (20% weight)
    """
    if not item_hash:
        return []
    
    all_items = Item.query.filter(
        Item.id != item_id, 
        Item.status != 'resolved'
    ).all()
    
    matches = []
    for item in all_items:
        # Calculate image hash similarity (50%)
        image_sim = calculate_similarity(item_hash, item.image_hash) if item.image_hash else 0
        
        # Calculate text similarity (30%)
        text_sim = 0
        if item_description and item.description:
            text_sim = calculate_text_similarity(item_description, item.description)
        
        # Item type similarity (20%)
        type_sim = 0
        if item_type and item.item_type:
            if item_type.lower() == item.item_type.lower():
                type_sim = 100
            elif item_type.lower() in item.item_type.lower() or item.item_type.lower() in item_type.lower():
                type_sim = 50
        
        # Weighted final score
        final_score = (image_sim * 0.5) + (text_sim * 0.3) + (type_sim * 0.2)
        
        if final_score > 55:
            matches.append({
                'item': item, 
                'similarity': round(final_score, 1),
                'image_match': round(image_sim, 1),
                'text_match': round(text_sim, 1)
            })
    
    return sorted(matches, key=lambda x: x['similarity'], reverse=True)[:10]

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
        
        # AI: Auto-predict category if not selected
        if not item_type or item_type == '':
            predicted = predict_category(title, description)
            if predicted:
                item_type = predicted
        
        location = request.form.get('location')
        campus_area = request.form.get('campus_area')
        image_path = None
        image_hash = None
        dominant_colors = None
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(str(uuid.uuid4()) + '_' + file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_path = filename
                image_hash = get_image_hash(filepath)
                # Extract dominant colors for AI matching
                dominant_colors = extract_dominant_colors(filepath)
        
        new_item = Item(title=title, description=description, category=category, item_type=item_type, location=location, campus_area=campus_area, image_path=image_path, image_hash=image_hash, user_id=user_id)
        db.session.add(new_item)
        db.session.commit()
        
        # AI Matching
        if image_hash:
            matches = find_matches(new_item.id, image_hash, description, item_type)
            for match in matches:
                new_match = Match(found_item_id=match['item'].id if match['item'].category == 'found' else new_item.id, lost_item_id=new_item.id if match['item'].category == 'found' else match['item'].id, similarity=match['similarity'])
                db.session.add(new_match)
            db.session.commit()
        
        flash(f'{category.title()} item reported! AI auto-categorized as: {item_type}', 'success')
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

# AI Suggestions API
@app.route('/api/ai/suggestions')
def ai_suggestions():
    """Get AI-powered suggestions for an item."""
    item_id = request.args.get('item_id', type=int)
    if not item_id:
        return jsonify({'error': 'item_id required'}), 400
    
    item = Item.query.get(item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    suggestions = get_ai_suggestions(item.id, item.title, item.description, item.item_type, item.campus_area)
    
    return jsonify({
        'item_id': item_id,
        'suggestions': [
            {
                'id': s['item'].id,
                'title': s['item'].title,
                'category': s['item'].category,
                'campus_area': s['item'].campus_area,
                'score': s['score'],
                'image': url_for('static', filename='uploads/' + s['item'].image_path) if s['item'].image_path else None
            }
            for s in suggestions
        ]
    })

# AI Predict Category API
@app.route('/api/ai/predict-category', methods=['POST'])
def ai_predict_category():
    """Predict category based on title and description."""
    data = request.get_json()
    title = data.get('title', '')
    description = data.get('description', '')
    
    predicted = predict_category(title, description)
    
    return jsonify({
        'title': title,
        'predicted_category': predicted,
        'confidence': 'high' if predicted != 'Other' else 'low'
    })

# Edit Item
@app.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    user_id = request.args.get('user_id')
    user = User.query.get(user_id) if user_id else None
    
    # Check ownership
    if not user or item.user_id != user.id:
        flash('You can only edit your own items.', 'error')
        return redirect(url_for('dashboard', user_id=user_id))
    
    if request.method == 'POST':
        item.title = request.form.get('title')
        item.description = request.form.get('description')
        item.item_type = request.form.get('item_type')
        item.location = request.form.get('location')
        item.campus_area = request.form.get('campus_area')
        
        # Handle new image upload
        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            filename = secure_filename(str(uuid.uuid4()) + '_' + file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            item.image_path = filename
            item.image_hash = get_image_hash(filepath)
        
        db.session.commit()
        flash('Item updated successfully!', 'success')
        return redirect(url_for('item_detail', item_id=item.id, user_id=user_id))
    
    return render_template('edit_item.html', item=item, user=user)

# Delete Item
@app.route('/item/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    user_id = request.form.get('user_id')
    user = User.query.get(user_id) if user_id else None
    
    # Check ownership
    if not user or item.user_id != user.id:
        flash('You can only delete your own items.', 'error')
        return redirect(url_for('dashboard', user_id=user_id))
    
    # Delete associated matches
    Match.query.filter((Match.found_item_id == item_id) | (Match.lost_item_id == item_id)).delete()
    
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted successfully!', 'success')
    return redirect(url_for('dashboard', user_id=user_id))

# Contact Item Owner (without showing phone)
@app.route('/item/<int:item_id>/contact', methods=['POST'])
def contact_owner(item_id):
    item = Item.query.get_or_404(item_id)
    user_id = request.form.get('user_id')
    user = User.query.get(user_id) if user_id else None
    
    if not user:
        flash('Please login to contact the owner.', 'error')
        return redirect(url_for('login'))
    
    if item.user_id == user.id:
        flash('This is your own item!', 'error')
        return redirect(url_for('item_detail', item_id=item_id, user_id=user_id))
    
    # Get item owner info
    owner = User.query.get(item.user_id)
    
    # Show contact info (without exposing phone publicly)
    flash(f'Contact the owner at: {owner.email}', 'success')
    return redirect(url_for('item_detail', item_id=item_id, user_id=user_id))

# Mark Item as Resolved/Claimed
@app.route('/item/<int:item_id>/resolve', methods=['POST'])
def resolve_item(item_id):
    item = Item.query.get_or_404(item_id)
    user_id = request.form.get('user_id')
    user = User.query.get(user_id) if user_id else None
    
    if not user:
        flash('Please login to resolve items.', 'error')
        return redirect(url_for('login'))
    
    item.status = 'resolved'
    db.session.commit()
    flash('Item marked as resolved!', 'success')
    return redirect(url_for('dashboard', user_id=user_id))

# User Profile
@app.route('/profile')
def profile():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id) if user_id else None
    if not user:
        return redirect(url_for('login'))
    
    my_items = Item.query.filter_by(user_id=user_id).order_by(Item.created_at.desc()).all()
    lost_count = Item.query.filter_by(user_id=user_id, category='lost').count()
    found_count = Item.query.filter_by(user_id=user_id, category='found').count()
    resolved_count = Item.query.filter_by(user_id=user_id, status='resolved').count()
    
    return render_template('profile.html', user=user, my_items=my_items, 
                         lost_count=lost_count, found_count=found_count, resolved_count=resolved_count)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
