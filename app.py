# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import send_file, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import razorpay
import io
import os
try:
    from twilio.rest import Client
except Exception:
    Client = None
try:
    import qrcode
except ImportError:
    qrcode = None

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a-default-fallback-secret-key-for-dev')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')

db = SQLAlchemy(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Razorpay Configuration
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

UPI_ID = os.environ.get('UPI_ID', 'merchant@upi')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if Client and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# Delivery & Logistics Defaults
DEFAULT_SHIPPING_FEE = 60
DEFAULT_FREE_SHIPPING_THRESHOLD = 600
DEFAULT_DELIVERY_PARTNER_COST = 45
DEFAULT_COMMISSION_RATE = 0.10

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20))
    account_number = db.Column(db.String(50), nullable=True)
    upi_phone_number = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default='kg')
    image = db.Column(db.String(200))
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Add relationship to reviews
    reviews = db.relationship('ProductReview', backref='product', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def price_per_unit(self):
        return f"₹{self.price} / {self.unit}"

class ProductReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(50), nullable=False)
    shipping_address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Pending')
    delivery_fee = db.Column(db.Float, default=0.0)
    delivery_cost = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_person_id = db.Column(db.Integer, db.ForeignKey('delivery_person.id'), nullable=True)
    delivery_person = db.relationship('DeliveryPerson')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='SET NULL'), nullable=True)
    seller_id = db.Column(db.Integer, nullable=True)
    product_name = db.Column(db.String(100), nullable=False) # Snapshot of name
    price = db.Column(db.Float, nullable=False) # Snapshot of price
    quantity = db.Column(db.Integer, nullable=False)
    is_paid_to_seller = db.Column(db.Boolean, default=False)
    commission_amount = db.Column(db.Float, default=0.0)

class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class OrderNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note_text = db.Column(db.Text, nullable=False)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    author = db.relationship('User')

class DeliveryPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.Text, nullable=True)
    vehicle_type = db.Column(db.String(50), nullable=True, default='Bike')
    vehicle_number = db.Column(db.String(20), unique=True, nullable=False)
    license_number = db.Column(db.String(30), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    profile_picture = db.Column(db.String(200), nullable=True)
    license_image = db.Column(db.String(200), nullable=True)


class Payout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_ref = db.Column(db.String(100), nullable=True)
    commission_total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SiteSetting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=False)

# Create tables
with app.app_context():
    db.create_all()
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(user)')).fetchall()]
        if 'phone' not in cols:
            db.session.execute(db.text('ALTER TABLE user ADD COLUMN phone VARCHAR(20)'))
            db.session.commit()
    except Exception:
        pass
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(user)')).fetchall()]
        if 'account_number' not in cols:
            db.session.execute(db.text('ALTER TABLE user ADD COLUMN account_number VARCHAR(50)'))
        if 'upi_phone_number' not in cols:
            db.session.execute(db.text('ALTER TABLE user ADD COLUMN upi_phone_number VARCHAR(20)'))
        db.session.commit()
    except Exception:
        pass
    # Check for is_approved in user table
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(user)')).fetchall()]
        if 'is_approved' not in cols:
            db.session.execute(db.text('ALTER TABLE user ADD COLUMN is_approved BOOLEAN DEFAULT 1'))
            db.session.commit()
    except Exception:
        pass
    # Check for shipping_address in order table
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info("order")')).fetchall()]
        if 'shipping_address' not in cols:
            db.session.execute(db.text('ALTER TABLE "order" ADD COLUMN shipping_address TEXT'))
            db.session.commit()
    except Exception:
        pass
    # Check for delivery_fee and delivery_cost in order table
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info("order")')).fetchall()]
        if 'delivery_fee' not in cols:
            db.session.execute(db.text('ALTER TABLE "order" ADD COLUMN delivery_fee FLOAT DEFAULT 0.0'))
        if 'delivery_cost' not in cols:
            db.session.execute(db.text('ALTER TABLE "order" ADD COLUMN delivery_cost FLOAT DEFAULT 0.0'))
        if 'delivery_person_id' not in cols:
            db.session.execute(db.text('ALTER TABLE "order" ADD COLUMN delivery_person_id INTEGER REFERENCES delivery_person(id)'))
            db.session.commit()
    except Exception:
        pass
    # Check for unit in product table
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(product)')).fetchall()]
        if 'unit' not in cols:
            db.session.execute(db.text("ALTER TABLE product ADD COLUMN unit VARCHAR(20) DEFAULT 'kg'"))
            db.session.commit()
    except Exception:
        pass
    # Check for seller_id and is_paid_to_seller in order_item
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(order_item)')).fetchall()]
        if 'seller_id' not in cols:
            db.session.execute(db.text('ALTER TABLE order_item ADD COLUMN seller_id INTEGER'))
            # Backfill seller_id from product table for existing items
            db.session.execute(db.text('UPDATE order_item SET seller_id = (SELECT seller_id FROM product WHERE product.id = order_item.product_id) WHERE seller_id IS NULL'))
            db.session.commit()
        if 'is_paid_to_seller' not in cols:
            db.session.execute(db.text('ALTER TABLE order_item ADD COLUMN is_paid_to_seller BOOLEAN DEFAULT 0'))
            db.session.commit()
        if 'commission_amount' not in cols:
            db.session.execute(db.text('ALTER TABLE order_item ADD COLUMN commission_amount FLOAT DEFAULT 0.0'))
            # Backfill commission for existing items based on default rate
            db.session.execute(db.text(f'UPDATE order_item SET commission_amount = price * quantity * {DEFAULT_COMMISSION_RATE} WHERE commission_amount = 0.0'))
            db.session.commit()
    except Exception:
        pass
    # Check for commission_total in payout table
    try:
        cols = [r[1] for r in db.session.execute(db.text('PRAGMA table_info(payout)')).fetchall()]
        if 'commission_total' not in cols:
            db.session.execute(db.text('ALTER TABLE payout ADD COLUMN commission_total FLOAT DEFAULT 0.0'))
            db.session.commit()
    except Exception:
        pass
    # Initialize default settings
    try:
        if not SiteSetting.query.first():
            db.session.add(SiteSetting(key='shipping_fee', value=str(DEFAULT_SHIPPING_FEE)))
            db.session.add(SiteSetting(key='free_shipping_threshold', value=str(DEFAULT_FREE_SHIPPING_THRESHOLD)))
            db.session.add(SiteSetting(key='delivery_partner_cost', value=str(DEFAULT_DELIVERY_PARTNER_COST)))
            db.session.add(SiteSetting(key='commission_rate', value=str(DEFAULT_COMMISSION_RATE)))
            db.session.commit()
        # Ensure commission_rate exists if settings are already there
        elif not db.session.get(SiteSetting, 'commission_rate'):
             db.session.add(SiteSetting(key='commission_rate', value=str(DEFAULT_COMMISSION_RATE)))
             db.session.commit()
    except Exception:
        pass
    # Create admin user if not exists
    if not User.query.filter_by(role='admin').first():
        admin_user = User(
            name='Admin',
            email='admin@agrimarket.com',
            password=generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123')),
            role='admin'
        )
        db.session.add(admin_user)
        db.session.commit()

# Helper Decorator for role-based access
def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login first.', 'error')
                return redirect(url_for('login'))
            if session.get('user_role') not in roles:
                flash(f'Access denied. This page requires one of the following roles: {", ".join(roles)}.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper


def send_sms(to, message):
    try:
        if twilio_client and TWILIO_FROM_NUMBER and to:
            twilio_client.messages.create(to=to, from_=TWILIO_FROM_NUMBER, body=message)
            return True
    except Exception:
        return False
    return False

def send_reset_email(to_email, reset_link):
    """Sends password reset email or logs to console if SMTP not configured."""
    sender_email = os.environ.get('MAIL_USERNAME')
    sender_password = os.environ.get('MAIL_PASSWORD')
    smtp_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('MAIL_PORT', 587))

    # If credentials are missing, log to console for development
    if not sender_email or not sender_password:
        print(f"\n{'='*50}")
        print(f"[DEV MODE] Password Reset Link for {to_email}:")
        print(f"{reset_link}")
        print(f"{'='*50}\n")
        return True

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = "Password Reset Request - Cropify"

        body = f"Click the following link to reset your password: {reset_link}\n\nIf you did not request this, please ignore this email.\nLink expires in 1 hour."
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_notification_email(to_email, subject, body):
    """Sends a general notification email."""
    sender_email = os.environ.get('MAIL_USERNAME')
    sender_password = os.environ.get('MAIL_PASSWORD')
    smtp_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('MAIL_PORT', 587))

    # If credentials are missing, log to console for development
    if not sender_email or not sender_password:
        print(f"\n[DEV MODE] Email to {to_email}\nSubject: {subject}\nBody: {body}\n")
        return True

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def get_site_setting(key, default_val, type_func=float):
    """Helper to get a site setting with a default fallback."""
    try:
        setting = db.session.get(SiteSetting, key)
        if setting:
            return type_func(setting.value)
    except Exception:
        pass
    return default_val

def calculate_delivery_charges(distance_km):
    """Calculates delivery fee and cost based on distance and commission slabs."""
    try:
        distance_km = float(distance_km)
    except (ValueError, TypeError):
        # Default to a high tier if distance is invalid
        return 150, 100

    if distance_km <= 5:
        fee = 40
        cost = fee - 10  # 30
    elif distance_km <= 15:
        fee = 60
        cost = fee - 20  # 40
    elif distance_km <= 30:
        fee = 90
        cost = fee - 35  # 55
    else: # For distances > 30km, a higher flat rate
        fee = 150
        cost = 100 # 50 profit
    return fee, cost

def log_order_status(order_id, new_status, commit=True):
    """Logs a new status for an order."""
    history_entry = OrderStatusHistory(order_id=order_id, status=new_status)
    db.session.add(history_entry)
    if commit:
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            
            # Check approval status for sellers/farmers
            if user.role in ['seller', 'farmer'] and not user.is_approved:
                flash('Your account is pending approval by an admin. Please wait for approval.', 'warning')
                return render_template('login.html')

            session['user_name'] = user.name
            session['user_role'] = user.role
            
            flash('Login successful!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin'))
            elif user.role in ['seller', 'farmer']:
                return redirect(url_for('seller_dashboard'))
            else:
                return redirect(url_for('product'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        phone = request.form.get('phone')
        account_number = request.form.get('account_number')
        upi_phone_number = request.form.get('upi_phone_number')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        # Set approval status based on role
        is_approved = True
        if role in ['seller', 'farmer']:
            is_approved = False

        new_user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role=role,
            phone=phone,
            account_number=account_number,
            upi_phone_number=upi_phone_number,
            is_approved=is_approved
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        if not is_approved:
            flash('Registration successful! Your account is pending approval by an admin.', 'info')
        else:
            flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            link = url_for('reset_password', token=token, _external=True)
            send_reset_email(email, link)
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        else:
            # For security, we usually don't want to explicitly say "Email not found"
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # Token expires in 1 hour (3600 seconds)
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash('The reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
            
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Your password has been updated! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('User not found.', 'error')
            return redirect(url_for('login'))
            
    return render_template('reset_password.html', token=token)

@app.route('/product')
@roles_required('buyer', 'seller', 'admin', 'farmer')
def product():
    # Normalize category parameter and perform case-insensitive filtering
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Number of products per page
    category = request.args.get('category', 'all')
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'newest')  # Get sort param, default to 'newest'
    cat_key = (category or 'all').lower()

    query = Product.query
    
    if cat_key != 'all':
        # filter by lowercased category to be tolerant of stored casing
        query = query.filter(db.func.lower(Product.category) == cat_key)

    if search_query:
        query = query.filter(Product.name.ilike(f'%{search_query}%'))

    # Subquery to get average rating and review count for each product
    avg_rating_subquery = db.session.query(
        ProductReview.product_id,
        db.func.avg(ProductReview.rating).label('avg_rating'),
        db.func.count(ProductReview.id).label('review_count')
    ).group_by(ProductReview.product_id).subquery()

    # Join the main product query with the subquery
    query = query.outerjoin(avg_rating_subquery, Product.id == avg_rating_subquery.c.product_id)

    # Add sorting logic
    if sort_by == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'popular':
        # Order by review count descending, handling NULLs
        query = query.order_by(db.func.coalesce(avg_rating_subquery.c.review_count, 0).desc())
    else:  # 'newest' or default
        query = query.order_by(Product.created_at.desc())

    pagination = query.add_columns(
        avg_rating_subquery.c.avg_rating,
        avg_rating_subquery.c.review_count
    ).paginate(page=page, per_page=per_page, error_out=False)

    product_data = pagination.items

    # Process into a list of product objects with attached rating info
    products_with_ratings = []
    for p, avg_rating, review_count in product_data:
        p.avg_rating = avg_rating or 0
        p.review_count = review_count or 0
        products_with_ratings.append(p)

    # Compute cart count for current user (server-side)
    cart_count = 0
    if 'user_id' in session:
        cart_count = db.session.query(db.func.coalesce(db.func.sum(Cart.quantity), 0)).filter(Cart.buyer_id == session['user_id']).scalar() or 0

    # pass normalized category key and sort_by for template active state
    return render_template('product.html', product=products_with_ratings, category=cat_key, cart_count=cart_count, sort_by=sort_by, pagination=pagination)

@app.route('/addproduct', methods=['GET', 'POST'])
@roles_required('seller', 'farmer', 'admin')
def addproduct():
    units = ['kg', 'gram', 'liter', 'dozen', 'packet', 'piece']
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        unit = request.form.get('unit') or 'kg'
        image = request.form['image'] or None

        try:
            price = float(request.form.get('price'))
            quantity = int(request.form.get('quantity'))
        except (ValueError, TypeError):
            flash('Price and quantity must be valid numbers.', 'error')
            return render_template('addproduct.html', units=units, form_data=request.form)

        if price <= 0 or quantity <= 0:
            flash('Price and quantity must be positive values.', 'error')
            return render_template('addproduct.html', units=units, form_data=request.form)
        
        new_product = Product(
            name=name,
            category=category,
            price=price,
            quantity=quantity,
            unit=unit,
            image=image,
            seller_id=session['user_id']
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        flash(f'Product "{name}" added successfully! Price: ₹{price}/{unit}', 'success')
        return redirect(url_for('product'))
    
    return render_template('addproduct.html', units=units)

@app.route('/add_to_cart/<int:product_id>')
@roles_required('buyer')
def add_to_cart(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404

    # --- Stock Validation ---
    # Prevent adding more items than are in stock
    existing_quantity_in_cart = db.session.query(db.func.sum(Cart.quantity)).filter_by(buyer_id=session['user_id'], product_id=product_id).scalar() or 0
    if existing_quantity_in_cart >= product.quantity:
        return jsonify({'success': False, 'message': f'No more stock available for "{product.name}".'}), 400

    cart_item = Cart.query.filter_by(
        buyer_id=session['user_id'],
        product_id=product_id
    ).first()

    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = Cart(
            buyer_id=session['user_id'],
            product_id=product_id,
            quantity=1
        )
        db.session.add(cart_item)

    db.session.commit()

    # Get updated cart count
    new_cart_count = db.session.query(db.func.coalesce(db.func.sum(Cart.quantity), 0)).filter(Cart.buyer_id == session['user_id']).scalar() or 0

    return jsonify({'success': True, 'message': f'"{product.name}" added to cart!', 'cart_count': new_cart_count})

@app.route('/buy_now/<int:product_id>', methods=['POST'])
@roles_required('buyer')
def buy_now(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))

    if quantity <= 0 or quantity > product.quantity:
        flash('Invalid quantity or not enough stock.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    
    # --- New "Buy Now" Logic ---
    # 1. Clear the user's current cart to ensure it's a "buy now" flow
    Cart.query.filter_by(buyer_id=session['user_id']).delete()

    # 2. Add the new item to the now-empty cart
    new_cart_item = Cart(
        buyer_id=session['user_id'],
        product_id=product_id,
        quantity=quantity
    )
    db.session.add(new_cart_item)
    db.session.commit()
    
    flash('Proceed to checkout for your item.', 'info')
    # 3. Redirect to the checkout page to enter distance and complete purchase
    return redirect(url_for('checkout'))

def get_cart_details(user_id):
    """Helper function to get cart items and total amount."""
    cart_products = []
    total_amount = 0

    # Optimized query using a JOIN
    cart_items = db.session.query(Cart, Product).join(Product, Cart.product_id == Product.id).filter(Cart.buyer_id == user_id).all()

    for cart_item, product in cart_items:
        item_total = product.price * cart_item.quantity
        total_amount += item_total
        cart_products.append({
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'quantity': cart_item.quantity,
            'unit': product.unit,
            'total': item_total,
            'image': product.image,
            'seller_id': product.seller_id
        })
    
    return cart_products, total_amount


@app.context_processor
def inject_cart_count():
    """Inject `cart_count` into all templates for the navbar badge."""
    cart_count = 0
    try:
        if 'user_id' in session:
            cart_count = db.session.query(db.func.coalesce(db.func.sum(Cart.quantity), 0)).filter(Cart.buyer_id == session['user_id']).scalar() or 0
    except Exception:
        cart_count = 0
    return dict(cart_count=cart_count)

@app.route('/cart')
@roles_required('buyer')
def cart():
    cart_products, total_amount = get_cart_details(session['user_id'])
    return render_template('cart.html', cart_product=cart_products, total_amount=total_amount)

@app.route('/update_cart/<int:product_id>/<action>')
@roles_required('buyer')
def update_cart(product_id, action):
    cart_item = Cart.query.filter_by(buyer_id=session['user_id'], product_id=product_id).first()
    if cart_item:
        if action == 'increase':
            product = db.session.get(Product, product_id)
            if cart_item.quantity < product.quantity:
                cart_item.quantity += 1
                db.session.commit()
            else:
                flash(f'Cannot add more. Only {product.quantity} available.', 'warning')
        elif action == 'decrease':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                db.session.commit()
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:product_id>')
@roles_required('buyer')
def remove_from_cart(product_id):
    Cart.query.filter_by(buyer_id=session['user_id'], product_id=product_id).delete()
    db.session.commit()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))


@app.route('/clear_cart')
@roles_required('buyer')
def clear_cart():
    Cart.query.filter_by(buyer_id=session['user_id']).delete()
    db.session.commit()
    flash('Cart cleared.', 'info')
    return redirect(url_for('cart'))

@app.route('/generate_upi_qr')
@roles_required('buyer')
def generate_upi_qr():
    if not qrcode:
        return "QR Code library not installed", 500
    
    cart_products, total_amount = get_cart_details(session['user_id'])
    if not cart_products:
        return "Cart is empty", 400

    shipping_fee = get_site_setting('shipping_fee', DEFAULT_SHIPPING_FEE)
    free_shipping_threshold = get_site_setting('free_shipping_threshold', DEFAULT_FREE_SHIPPING_THRESHOLD)

    shipping = 0 if total_amount >= free_shipping_threshold else shipping_fee
    tax = total_amount * 0.05
    grand_total = total_amount + shipping + tax

    upi_url = f"upi://pay?pa={UPI_ID}&pn=E-Manddi&am={grand_total:.2f}&cu=INR"
    
    img = qrcode.make(upi_url)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/calculate_shipping', methods=['POST'])
def api_calculate_shipping():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'User not logged in'}), 401
        
    data = request.get_json()
    distance = data.get('distance')
    
    try:
        distance = float(distance)
        if distance < 0: raise ValueError
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid distance'}), 400

    delivery_fee, _ = calculate_delivery_charges(distance)
    
    _, total_amount = get_cart_details(session['user_id'])
    free_shipping_threshold = get_site_setting('free_shipping_threshold', DEFAULT_FREE_SHIPPING_THRESHOLD)
    
    shipping_charge = 0 if total_amount >= free_shipping_threshold else delivery_fee
    grand_total = total_amount + shipping_charge
    
    return jsonify({
        'success': True,
        'shipping_charge': shipping_charge,
        'grand_total': grand_total,
        'is_free': shipping_charge == 0
    })

@app.route('/create-payment', methods=['POST'])
@roles_required('buyer')
def create_payment():
    """Create Razorpay order for payment"""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        app.logger.error("Razorpay keys are not configured.")
        return jsonify({'error': 'Online payment is not configured.'}), 500

    try:
        cart_products, total_amount = get_cart_details(session['user_id'])
        
        if not cart_products:
            return jsonify({'error': 'Cart is empty'}), 400
        
        # Get distance from request
        data = request.get_json()
        distance = data.get('distance')
        
        if not distance:
            return jsonify({'error': 'Distance is required'}), 400
            
        delivery_fee, _ = calculate_delivery_charges(distance)
        
        # Calculate shipping
        free_shipping_threshold = get_site_setting('free_shipping_threshold', DEFAULT_FREE_SHIPPING_THRESHOLD)
        shipping_charge = 0 if total_amount >= free_shipping_threshold else delivery_fee
        grand_total = total_amount + shipping_charge

        # Create Razorpay order
        order_amount = int(grand_total * 100)  # Amount in paise
        order_data = {
            'amount': order_amount,
            'currency': 'INR',
            'receipt': f"order_{session['user_id']}_{int(datetime.utcnow().timestamp())}",
            'payment_capture': '1'  # Auto capture payment
        }
        
        razorpay_order = razorpay_client.order.create(order_data)
        
        return jsonify({
            'order_id': razorpay_order['id'],
            'amount': order_amount,
            'key_id': RAZORPAY_KEY_ID,
            'user_email': session.get('user_email', 'user@cropify.com'),
            'user_phone': '9999999999'
        })
    except Exception as e:
        app.logger.error(f"Error creating Razorpay order: {e}")
        return jsonify({'error': str(e)}), 400

def _process_order_items_and_stock(user_id, new_order, cart_products):
    """
    Helper function to:
    1. Create OrderItem entries for an order.
    2. Decrease product stock.
    3. Delete products if stock runs out.
    4. Clear the user's cart.
    """
    commission_rate = get_site_setting('commission_rate', DEFAULT_COMMISSION_RATE)
    seller_items_map = {} # Map seller_id to list of product names for notification

    for item in cart_products:
        item_total = item['price'] * item['quantity']
        commission = item_total * commission_rate
        order_item = OrderItem(order_id=new_order.id, product_id=item['id'], seller_id=item['seller_id'], product_name=item['name'], price=item['price'], quantity=item['quantity'], commission_amount=commission)
        db.session.add(order_item)

        # Group items by seller for notification
        sid = item['seller_id']
        if sid not in seller_items_map:
            seller_items_map[sid] = []
        seller_items_map[sid].append(f"{item['name']} (Qty: {item['quantity']})")

    cart_items = db.session.query(Cart).filter_by(buyer_id=user_id).all()
    for item in cart_items:
        product = db.session.get(Product, item.product_id)
        if product:
            product.quantity -= item.quantity
            if product.quantity <= 0:
                app.logger.info(f'Product "{product.name}" (ID: {product.id}) ran out of stock and was deleted.')
                db.session.delete(product)
    # Clear cart after processing stock
    Cart.query.filter_by(buyer_id=user_id).delete()

    # Send notifications to sellers
    for sid, products_list in seller_items_map.items():
        seller = db.session.get(User, sid)
        if seller and seller.phone:
            product_str = ", ".join(products_list)
            msg = f"New Order! You have sold: {product_str}. Check your dashboard."
            send_sms(seller.phone, msg)

@app.route('/verify-payment', methods=['POST'])
@roles_required('buyer')
def verify_payment():
    """Verify Razorpay payment signature and create order"""
    try:
        data = request.json
        if not all(k in data for k in ['razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature']):
            return jsonify({'error': 'Missing payment verification data'}), 400
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            return jsonify({'error': 'Payment verification is not configured'}), 500
        
        # Verify payment signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })
        
        # Payment verified - get cart details
        # We get details *before* clearing the cart
        cart_products, total_amount = get_cart_details(session['user_id'])
        
        shipping_address = data.get('shipping_address', '')
        distance = data.get('distance')
        
        # Calculate delivery charges based on distance
        delivery_fee, delivery_cost = calculate_delivery_charges(distance)
        
        # Calculate shipping
        free_shipping_threshold = get_site_setting('free_shipping_threshold', DEFAULT_FREE_SHIPPING_THRESHOLD)
        shipping_charge = 0 if total_amount >= free_shipping_threshold else delivery_fee
        grand_total = total_amount + shipping_charge

        # Create order in database
        new_order = Order(
            buyer_id=session['user_id'],
            total_amount=grand_total,
            payment_mode='Razorpay',
            shipping_address=shipping_address,
            status='Confirmed',
            delivery_fee=shipping_charge,
            delivery_cost=delivery_cost
        )
        
        db.session.add(new_order)
        db.session.flush()  # Flush to get the new_order.id before using it
        log_order_status(new_order.id, new_order.status, commit=False)

        # Process order items, stock, and clear cart
        _process_order_items_and_stock(session['user_id'], new_order, cart_products)

        db.session.commit()
        
        flash('Payment successful! Order placed.', 'success')
        buyer = db.session.get(User, session['user_id'])
        if buyer and buyer.phone:
            send_sms(buyer.phone, f'Payment received. Order #{new_order.id} placed')
        return jsonify({'success': True, 'order_id': new_order.id})
    
    except razorpay.errors.SignatureVerificationError:
        app.logger.warning("Razorpay signature verification failed.")
        return jsonify({'error': 'Payment verification failed'}), 400
    except Exception as e:
        app.logger.error(f"Error verifying payment: {e}")
        return jsonify({'error': str(e)}), 400
    
    
@app.route('/checkout', methods=['GET', 'POST'])
@roles_required('buyer')
def checkout():
    cart_products, total_amount = get_cart_details(session['user_id'])

    if not cart_products:
        flash('Your cart is empty. Add some products before checking out.', 'info')
        return redirect(url_for('product'))
    
    # Calculate shipping
    # For display on GET request, we show the default flat rate as an estimate.
    # The final calculation happens on POST.
    initial_shipping_fee = get_site_setting('shipping_fee', DEFAULT_SHIPPING_FEE)
    free_shipping_threshold = get_site_setting('free_shipping_threshold', DEFAULT_FREE_SHIPPING_THRESHOLD)

    shipping_charge = 0 if total_amount >= free_shipping_threshold else initial_shipping_fee
    grand_total = total_amount + shipping_charge # This is an initial estimate for display

    if request.method == 'POST':
        payment_mode = request.form['payment_mode']
        shipping_address = request.form.get('shipping_address')
        distance_str = request.form.get('distance')

        if not shipping_address:
            flash('Shipping address is required.', 'error')
            return redirect(url_for('checkout'))
        
        if not distance_str:
            flash('Distance is required for calculating delivery charges.', 'error')
            return redirect(url_for('checkout'))
        
        try:
            distance = float(distance_str)
            if distance < 0: raise ValueError
        except (ValueError, TypeError):
            flash('Please enter a valid, positive distance.', 'error')
            return redirect(url_for('checkout'))

        # This part handles COD/UPI form submissions
        if payment_mode in ['COD', 'UPI']:
            delivery_fee, delivery_cost = calculate_delivery_charges(distance)
            shipping_charge_for_customer = 0 if total_amount >= free_shipping_threshold else delivery_fee
            final_grand_total = total_amount + shipping_charge_for_customer

            new_order = Order(
                buyer_id=session['user_id'],
                total_amount=final_grand_total,
                payment_mode=payment_mode,
                shipping_address=shipping_address,
                status='Confirmed',
                delivery_fee=shipping_charge_for_customer,
                delivery_cost=delivery_cost
            )
            db.session.add(new_order)
            db.session.flush()
            log_order_status(new_order.id, new_order.status, commit=False)
            _process_order_items_and_stock(session['user_id'], new_order, cart_products)
            db.session.commit()
            flash('Order placed successfully!', 'success')
            return redirect(url_for('orderconformation', order_id=new_order.id))
    
    return render_template('checkout.html', cart_product=cart_products, total_amount=total_amount, shipping_charge=shipping_charge, grand_total=grand_total, upi_qr_url=url_for('generate_upi_qr'), upi_id=UPI_ID)

@app.route('/my_orders')
@roles_required('buyer')
def my_orders():
    """Allow buyers to see their order history."""
    orders = Order.query.filter_by(buyer_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)

@app.route('/track_order/<int:order_id>')
@roles_required('buyer')
def track_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Security check: ensure the order belongs to the logged-in buyer
    if order.buyer_id != session['user_id']:
        flash('You are not authorized to view this order.', 'error')
        return redirect(url_for('my_orders'))
 
    status_history = OrderStatusHistory.query.filter_by(order_id=order.id).order_by(OrderStatusHistory.timestamp.asc()).all()
    order_notes = OrderNote.query.filter_by(order_id=order.id, is_public=True).options(db.joinedload(OrderNote.author)).order_by(OrderNote.created_at.asc()).all()
    
    # Backfill initial status if it's missing for older orders
    if not status_history:
        log_order_status(order.id, order.status)
        status_history = OrderStatusHistory.query.filter_by(order_id=order.id).order_by(OrderStatusHistory.timestamp.asc()).all()

    # Combine and sort timeline events
    timeline_events = []
    for history in status_history:
        timeline_events.append({'type': 'status', 'data': history, 'timestamp': history.timestamp})
    for note in order_notes:
        timeline_events.append({'type': 'note', 'data': note, 'timestamp': note.created_at})
    
    timeline_events.sort(key=lambda x: x['timestamp'])

    return render_template('track_order.html', order=order, timeline_events=timeline_events)

@app.route('/orderconformation/<int:order_id>')
@roles_required('buyer', 'admin')
def orderconformation(order_id):
    order = Order.query.get_or_404(order_id)
    # Security check to ensure user can only see their own order unless they are an admin
    if order.buyer_id != session['user_id'] and session['user_role'] != 'admin':
        flash('You are not authorized to view this order.', 'error')
        return redirect(url_for('index'))

    buyer = db.session.get(User, order.buyer_id)
    order_items = db.session.query(OrderItem).filter_by(order_id=order.id).all()

    # To show a price breakdown, we calculate subtotal from items
    subtotal = sum(item.price * item.quantity for item in order_items)
    
    # The shipping charge is the difference between the grand total and the subtotal
    shipping_charge = order.total_amount - subtotal

    return render_template(
        'orderconformation.html', 
        order=order,
        buyer=buyer,
        order_items=order_items,
        subtotal=subtotal,
        shipping_charge=shipping_charge
    )
@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'user_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        rating = request.form['rating']
        message = request.form['message']
        
        new_feedback = Feedback(
            buyer_id=session['user_id'],
            rating=rating,
            message=message
        )
        
        db.session.add(new_feedback)
        db.session.commit()
        
        flash('Thank you for your feedback!', 'success')
        return redirect(url_for('thankyou'))
    
    return render_template('feedback.html')

@app.route('/thankyou')
def thankyou():
    return render_template(
        'thankyou.html')

@app.route('/admin')
@roles_required('admin')
def admin():
    today = datetime.now().date()
    current_month = today.month

    # Today's orders and sales
    today_orders = Order.query.filter(db.func.date(Order.created_at) == today).all()
    today_orders_count = Order.query.filter(db.func.date(Order.created_at) == today).count()
    today_sales = sum(order.total_amount for order in today_orders)
    # Yesterday's sales (for comparison)
    yesterday = today - timedelta(days=1)
    yesterday_sales = db.session.query(db.func.sum(Order.total_amount)).filter(db.func.date(Order.created_at) == yesterday).scalar() or 0
    # All-time stats
    total_orders_count = Order.query.count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_users_count = User.query.count()
    total_products_count = Product.query.count()

    # Calculate delivery earnings (Profit from logistics)
    total_delivery_earnings = db.session.query(db.func.sum(Order.delivery_fee - Order.delivery_cost)).scalar() or 0

    # Calculate total platform earnings from commission
    total_platform_earnings = db.session.query(
        db.func.sum(OrderItem.commission_amount)
    ).join(Order, OrderItem.order_id == Order.id)\
     .filter(
         Order.status.in_(['Delivered', 'Completed'])
     ).scalar() or 0

    # Calculate total pending payouts for dashboard widget
    total_pending_payouts = db.session.query(
        db.func.sum((OrderItem.price * OrderItem.quantity) - OrderItem.commission_amount)
    ).join(Order, OrderItem.order_id == Order.id)\
     .filter(
         OrderItem.is_paid_to_seller == False,
         Order.status.in_(['Delivered', 'Completed'])
     ).scalar() or 0

    # Fetch all products for the management table
    all_products = Product.query.order_by(Product.created_at.desc()).all()

    # Chart Data (last 7 days) - Sales by month/day
    sales_labels = []
    sales_values = []
    shipping_revenue_values = []
    delivery_cost_values = []
    produce_sales_values = []
    supplies_sales_values = []
    produce_cats = ['fruits', 'vegetables', 'grains', 'dairy']
    supplies_cats = ['seeds', 'fertilizers', 'pesticides', 'tools', 'machinery']

    for i in range(7):
        day = today - timedelta(days=i)
        day_sales = db.session.query(db.func.sum(Order.total_amount)).filter(db.func.date(Order.created_at) == day).scalar() or 0
        sales_labels.insert(0, day.strftime('%b %d'))
        sales_values.insert(0, day_sales)
        
        day_shipping = db.session.query(db.func.sum(Order.delivery_fee)).filter(db.func.date(Order.created_at) == day).scalar() or 0
        day_cost = db.session.query(db.func.sum(Order.delivery_cost)).filter(db.func.date(Order.created_at) == day).scalar() or 0
        shipping_revenue_values.insert(0, day_shipping)
        delivery_cost_values.insert(0, day_cost)

        # Calculate Produce Sales
        day_produce_sales = db.session.query(db.func.sum(OrderItem.price * OrderItem.quantity))\
            .join(Product, OrderItem.product_id == Product.id)\
            .join(Order, OrderItem.order_id == Order.id)\
            .filter(db.func.date(Order.created_at) == day)\
            .filter(Product.category.in_(produce_cats))\
            .scalar() or 0
        produce_sales_values.insert(0, day_produce_sales)

        # Calculate Supplies Sales
        day_supplies_sales = db.session.query(db.func.sum(OrderItem.price * OrderItem.quantity))\
            .join(Product, OrderItem.product_id == Product.id)\
            .join(Order, OrderItem.order_id == Order.id)\
            .filter(db.func.date(Order.created_at) == day)\
            .filter(Product.category.in_(supplies_cats))\
            .scalar() or 0
        supplies_sales_values.insert(0, day_supplies_sales)
    
    sales_by_month = {
        'labels': sales_labels,
        'data': sales_values
    }

    # Products by Category chart data
    categories = db.session.query(Product.category, db.func.count(Product.id)).group_by(Product.category).all()
    products_by_category = {
        'labels': [cat[0] for cat in categories],
        'data': [cat[1] for cat in categories]
    }

    # Weekly and Monthly totals
    week_sales = sum(sales_values)
    # Month: sum orders where month == current month and year == current year
    month_sales = db.session.query(db.func.sum(Order.total_amount)).filter(db.extract('month', Order.created_at) == today.month, db.extract('year', Order.created_at) == today.year).scalar() or 0

    # Pending orders
    pending_orders_count = Order.query.filter_by(status='Pending').count()

    # Pending user approvals
    pending_approvals_count = User.query.filter_by(is_approved=False).count()

    # Low stock alerts (threshold = 5)
    low_stock_threshold = 5
    low_stock_products = Product.query.filter(Product.quantity <= low_stock_threshold).order_by(Product.quantity.asc()).all()
    low_stock_count = Product.query.filter(Product.quantity <= low_stock_threshold).count()

    # Get recent users and feedback for "Recent Users" table (limited)
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all() # This is fine
    
    # Fetch recent feedback with user names
    recent_feedback = db.session.query(Feedback, User.name.label('user_name')).join(User, Feedback.buyer_id == User.id).order_by(Feedback.created_at.desc()).limit(5).all()
    
    # Fetch recent orders with user names
    recent_orders = db.session.query(Order, User.name.label('customer_name')).join(User, Order.buyer_id == User.id).order_by(Order.created_at.desc()).limit(5).all()

    # Efficiently compute customer summary with totals using database aggregation
    customers_summary = db.session.query(
        User,
        db.func.count(Order.id).label('total_orders'),
        db.func.sum(Order.total_amount).label('total_amount'),
        db.func.max(Order.created_at).label('last_order_date')
    ).join(Order, User.id == Order.buyer_id).group_by(User.id).order_by(db.desc('total_amount')).limit(10).all()

    # Top Products: Join with Product to get image and other details
    top_products = db.session.query(
        Product.id,
        Product.name,
        Product.image,
        db.func.sum(OrderItem.quantity).label('sales'),
        db.func.sum(OrderItem.price * OrderItem.quantity).label('revenue')
    ).join(Product, OrderItem.product_id == Product.id).group_by(Product.id, Product.name, Product.image).order_by(db.desc('revenue')).limit(5).all()

    # Provide footer timestamps for the template
    current_year = datetime.now().year
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template(
        'admin.html',
        today_sales=today_sales,
        today_orders_count=today_orders_count,
        total_sales=total_sales,
        total_orders_count=total_orders_count,
        total_users_count=total_users_count,
        total_products_count=total_products_count,
        total_delivery_earnings=total_delivery_earnings,
        total_platform_earnings=total_platform_earnings,
        recent_orders=recent_orders,
        users=recent_users,
        all_products=all_products,
        customers_summary=customers_summary,
        top_products=top_products,
        recent_feedback=recent_feedback,
        sales_by_month=sales_by_month,
        products_by_category=products_by_category,
        chart_labels=sales_labels,
        chart_values=sales_values,
        shipping_revenue_values=shipping_revenue_values,
        delivery_cost_values=delivery_cost_values,
        produce_sales_values=produce_sales_values,
        supplies_sales_values=supplies_sales_values,
        week_sales=week_sales,
        month_sales=month_sales,
        pending_orders_count=pending_orders_count,
        pending_approvals_count=pending_approvals_count,
        low_stock_count=low_stock_count,
        low_stock_products=low_stock_products,
        low_stock_threshold=low_stock_threshold,
        yesterday_sales=yesterday_sales,
        current_year=current_year,
        current_time=current_time,
        total_pending_payouts=total_pending_payouts,
        active_page='dashboard'
    )
    
@app.route('/admin/orders')
@roles_required('admin')
def admin_orders():
    """Dedicated page for viewing and managing all orders."""
    page = request.args.get('page', 1, type=int)
    per_page = 15
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()
    delivery_person_filter = request.args.get('delivery_person', type=int)

    # Query with pagination
    orders_query = db.session.query(
        Order, User.name.label('customer_name')
    ).join(User, Order.buyer_id == User.id)\
     .options(db.joinedload(Order.delivery_person))

    if delivery_person_filter:
        orders_query = orders_query.filter(Order.delivery_person_id == delivery_person_filter)

    orders_pagination = orders_query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Fetch active delivery persons for the assignment modal
    delivery_persons = DeliveryPerson.query.filter_by(is_active=True).order_by(DeliveryPerson.name).all()

    return render_template('admin_orders.html', 
                           orders_pagination=orders_pagination, 
                           delivery_persons=delivery_persons,
                           delivery_person_filter=delivery_person_filter,
                           active_page='orders',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count,
                           total_sales=total_sales,
                           total_orders_count=total_orders_count,
                           total_users_count=total_users_count,
                           total_products_count=total_products_count)

@app.route('/admin/assign_delivery_person/<int:order_id>', methods=['POST'])
@roles_required('admin')
def assign_delivery_person(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    person_id = data.get('person_id')

    # Handle un-assignment
    if not person_id or person_id == 'None' or person_id == '':
        order.delivery_person_id = None
        db.session.commit()
        return jsonify({'success': True, 'message': f'Order #{order.id} unassigned.'})

    person = DeliveryPerson.query.get(person_id)
    if not person or not person.is_active:
        return jsonify({'success': False, 'error': 'Invalid or inactive delivery person.'}), 400

    order.delivery_person_id = person.id
    db.session.commit()

    if person.phone:
        buyer = User.query.get(order.buyer_id)
        message = f"New delivery: Order #{order.id} for {buyer.name}. Address: {order.shipping_address}. Amount: Rs.{order.total_amount:.2f}"
        send_sms(person.phone, message)

    return jsonify({'success': True, 'message': f'{person.name} assigned to order #{order.id}.', 'person_name': person.name})

@app.route('/admin/analytics')
@roles_required('admin')
def admin_analytics():
    """Dedicated page for more detailed analytics."""
    period = request.args.get('period', 'monthly')  # Default to 'monthly'
    today = datetime.now().date()
    
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()

    sales_labels = []
    sales_values = []

    if period == 'weekly':
        # Sales data for the last 7 days
        for i in range(7):
            day = today - timedelta(days=i)
            day_sales = db.session.query(db.func.sum(Order.total_amount)).filter(db.func.date(Order.created_at) == day).scalar() or 0
            sales_labels.insert(0, day.strftime('%a, %b %d'))
            sales_values.insert(0, day_sales)
    elif period == 'yearly':
        # Sales data for the last 12 months
        current_year = today.year
        current_month = today.month
        for i in range(12):
            month = current_month - i
            year = current_year
            if month <= 0:
                month += 12
                year -= 1
            
            month_sales = db.session.query(db.func.sum(Order.total_amount)).filter(
                db.extract('year', Order.created_at) == year,
                db.extract('month', Order.created_at) == month
            ).scalar() or 0
            
            month_date = datetime(year, month, 1)
            sales_labels.insert(0, month_date.strftime('%b %Y'))
            sales_values.insert(0, month_sales)
    else:  # Default to 'monthly' (last 30 days)
        for i in range(30):
            day = today - timedelta(days=i)
            day_sales = db.session.query(db.func.sum(Order.total_amount)).filter(db.func.date(Order.created_at) == day).scalar() or 0
            sales_labels.insert(0, day.strftime('%b %d'))
            sales_values.insert(0, day_sales)

    # Category distribution
    categories = db.session.query(Product.category, db.func.count(Product.id)).group_by(Product.category).all()
    products_by_category = {
        'labels': [cat[0] for cat in categories],
        'data': [cat[1] for cat in categories]
    }

    return render_template('admin_analytics.html', 
                           chart_labels=sales_labels, 
                           chart_values=sales_values,
                           products_by_category=products_by_category,
                           period=period,
                           active_page='analytics',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count,
                           total_sales=total_sales,
                           total_orders_count=total_orders_count,
                           total_users_count=total_users_count,
                           total_products_count=total_products_count)

@app.route('/admin/products')
@roles_required('admin')
def admin_products():
    """Dedicated page for viewing and managing all products."""
    page = request.args.get('page', 1, type=int)
    per_page = 15
    low_stock_threshold = 5
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()
    low_stock_count = Product.query.filter(Product.quantity <= low_stock_threshold).count()
    search_query = request.args.get('q', '').strip()
    filter_type = request.args.get('filter', 'all')

    # Query with pagination
    query = Product.query
    if search_query:
        query = query.filter(Product.name.ilike(f'%{search_query}%'))
    
    # Apply category filter
    if filter_type == 'produce':
        query = query.filter(Product.category.in_(['fruits', 'vegetables', 'grains', 'dairy']))
    elif filter_type == 'supplies':
        query = query.filter(Product.category.in_(['seeds', 'fertilizers', 'pesticides', 'tools', 'machinery']))
    
    products_pagination = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Prepare data for JavaScript
    products_data = [
        {
            'id': p.id, 'name': p.name, 'category': p.category, 'price': p.price, 
            'quantity': p.quantity, 'unit': p.unit, 'seller_id': p.seller_id, 'image': p.image,
            'created_at': p.created_at.strftime('%Y-%m-%d')
        } for p in products_pagination.items
    ]

    return render_template(
        'admin_products.html',
        products_pagination=products_pagination,
        products_data=products_data,
        low_stock_threshold=low_stock_threshold,
        active_page='products',
        pending_orders_count=pending_orders_count,
        low_stock_count=low_stock_count,
        total_sales=total_sales,
        total_orders_count=total_orders_count,
        total_users_count=total_users_count,
        total_products_count=total_products_count,
        search_query=search_query,
        filter_type=filter_type
    )

@app.route('/admin/users')
@roles_required('admin')
def admin_users():
    """Dedicated page for viewing and managing all users."""
    page = request.args.get('page', 1, type=int)
    per_page = 15
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()
    search_query = request.args.get('q', '').strip()

    # Query with pagination
    query = User.query
    if search_query:
        query = query.filter(db.or_(User.name.ilike(f'%{search_query}%'), User.email.ilike(f'%{search_query}%')))
        
    users_pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Prepare data for JavaScript
    users_data = [
        {
            'id': u.id, 'name': u.name, 'email': u.email, 'phone': u.phone, 
            'role': u.role, 'created_at': u.created_at.strftime('%Y-%m-%d'),
            'account_number': u.account_number,
            'upi_phone_number': u.upi_phone_number,
            'is_approved': u.is_approved
        } for u in users_pagination.items
    ]

    return render_template('admin_users.html', 
                           users_pagination=users_pagination, 
                           users_data=users_data,
                           active_page='users',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count,
                           total_sales=total_sales,
                           total_orders_count=total_orders_count,
                           total_users_count=total_users_count,
                           total_products_count=total_products_count,
                           search_query=search_query)

@app.route('/admin/approve_user/<int:user_id>', methods=['POST'])
@roles_required('admin')
def admin_approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    
    if user.phone:
        send_sms(user.phone, "Your account has been approved! You can now log in and start selling.")
    
    flash(f'User {user.name} approved successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/categories')
@roles_required('admin')
def admin_categories():
    """Dedicated page for viewing product categories."""
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()
    # Query to get category name and count of products in it
    categories = db.session.query(
        Product.category, 
        db.func.count(Product.id).label('product_count')
    ).group_by(Product.category).order_by(Product.category).all()
    
    return render_template('admin_categories.html', 
                           categories=categories, 
                           active_page='categories',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count,
                           total_sales=total_sales,
                           total_orders_count=total_orders_count,
                           total_users_count=total_users_count,
                           total_products_count=total_products_count)

@app.route('/admin/settings', methods=['GET', 'POST'])
@roles_required('admin')
def admin_settings():
    """Dedicated page for admin settings."""
    if request.method == 'POST':
        shipping_fee = request.form.get('shipping_fee')
        free_shipping_threshold = request.form.get('free_shipping_threshold')
        delivery_partner_cost = request.form.get('delivery_partner_cost')
        commission_rate_percent = request.form.get('commission_rate')
        
        settings_map = {
            'shipping_fee': shipping_fee,
            'free_shipping_threshold': free_shipping_threshold,
            'delivery_partner_cost': delivery_partner_cost
        }
        
        for key, val in settings_map.items():
            if val is not None:
                setting = SiteSetting.query.get(key)
                if not setting:
                    setting = SiteSetting(key=key, value=str(val))
                    db.session.add(setting)
                else:
                    setting.value = str(val)
        
        # Handle commission rate separately to convert from %
        if commission_rate_percent is not None:
            try:
                rate_as_float = float(commission_rate_percent) / 100.0
                commission_setting = SiteSetting.query.get('commission_rate')
                if not commission_setting:
                    commission_setting = SiteSetting(key='commission_rate', value=str(rate_as_float))
                    db.session.add(commission_setting)
                else:
                    commission_setting.value = str(rate_as_float)
            except (ValueError, TypeError):
                flash('Invalid commission rate. Please enter a number.', 'error')

        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('admin_settings'))

    settings = {s.key: s.value for s in SiteSetting.query.all()}
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    return render_template('admin_settings.html', settings=settings, active_page='settings',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count)

@app.route('/admin/reviews')
@roles_required('admin')
def admin_reviews():
    """Dedicated page for viewing all feedback/reviews."""
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders_count = Order.query.count()
    total_users_count = User.query.count()
    total_products_count = Product.query.count()
    reviews = db.session.query(Feedback, User.name.label('user_name')).join(User, Feedback.buyer_id == User.id).order_by(Feedback.created_at.desc()).all()
    
    return render_template('admin_reviews.html', 
                           reviews=reviews, 
                           active_page='reviews',
                           pending_orders_count=pending_orders_count,
                           low_stock_count=low_stock_count,
                           total_sales=total_sales,
                           total_orders_count=total_orders_count,
                           total_users_count=total_users_count,
                           total_products_count=total_products_count)


@app.route('/admin/remove_user/<int:user_id>', methods=['POST'])
@roles_required('admin')
def remove_user(user_id):
    """Remove a user from the database"""
    try:
        user = db.session.get(User, user_id)
        if not user:
            return {'error': 'User not found'}, 404
        
        # With ondelete='CASCADE' in models, related records in Cart, Order,
        # Feedback, and Product (if seller) will be deleted automatically.
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        return {'success': True, 'message': f'User {user.name} removed successfully'}, 200
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500

@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
@roles_required('admin')
def admin_delete_product(product_id):
    """Allows an admin to delete any product."""
    try:
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404

        product_name = product.name
        db.session.delete(product)
        db.session.commit()

        return jsonify({'success': True, 'message': f'Product "{product_name}" has been deleted.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@roles_required('admin')
def admin_edit_product(product_id):
    """Handles fetching and updating a product for an admin."""
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': product.id,
            'name': product.name,
            'category': product.category,
            'price': product.price,
            'quantity': product.quantity,
            'unit': product.unit
        }), 200

    if request.method == 'POST':
        data = request.get_json()
        try:
            product.name = data.get('name', product.name)
            product.category = data.get('category', product.category)
            product.price = float(data.get('price', product.price))
            product.quantity = int(data.get('quantity', product.quantity))
            product.unit = data.get('unit', product.unit)
            db.session.commit()
            return jsonify({'success': True, 'message': f'Product "{product.name}" updated successfully.'}), 200
        except (ValueError, TypeError) as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Invalid data format.'}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/chart-data')
@roles_required('admin')
def admin_chart_data():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=6)

    # Helper to get dict of date->value
    def get_daily_sums(query):
        results = query.group_by(db.func.date(Order.created_at)).all()
        return {str(r[0]): r[1] for r in results}

    # Sales
    sales_query = db.session.query(
        db.func.date(Order.created_at),
        db.func.sum(Order.total_amount)
    ).filter(
        db.func.date(Order.created_at) >= start_date,
        db.func.date(Order.created_at) <= end_date
    )
    sales_map = get_daily_sums(sales_query)

    # Produce
    produce_cats = ['fruits', 'vegetables', 'grains', 'dairy']
    produce_query = db.session.query(
        db.func.date(Order.created_at),
        db.func.sum(OrderItem.price * OrderItem.quantity)
    ).join(Product, OrderItem.product_id == Product.id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .filter(
        db.func.date(Order.created_at) >= start_date,
        db.func.date(Order.created_at) <= end_date,
        Product.category.in_(produce_cats)
    )
    produce_map = get_daily_sums(produce_query)

    # Supplies
    supplies_cats = ['seeds', 'fertilizers', 'pesticides', 'tools', 'machinery']
    supplies_query = db.session.query(
        db.func.date(Order.created_at),
        db.func.sum(OrderItem.price * OrderItem.quantity)
    ).join(Product, OrderItem.product_id == Product.id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .filter(
        db.func.date(Order.created_at) >= start_date,
        db.func.date(Order.created_at) <= end_date,
        Product.category.in_(supplies_cats)
    )
    supplies_map = get_daily_sums(supplies_query)

    labels = []
    sales_values = []
    produce_values = []
    supplies_values = []

    delta = (end_date - start_date).days + 1
    for i in range(delta):
        day = start_date + timedelta(days=i)
        day_str = str(day)
        labels.append(day.strftime('%b %d'))
        sales_values.append(sales_map.get(day_str, 0))
        produce_values.append(produce_map.get(day_str, 0))
        supplies_values.append(supplies_map.get(day_str, 0))

    return jsonify({
        'labels': labels,
        'sales': sales_values,
        'produce': produce_values,
        'supplies': supplies_values
    })

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
@roles_required('admin')
def admin_update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    new_status = data.get('status')
    if new_status in ['Pending', 'Confirmed', 'Shipped', 'Delivered', 'Cancelled', 'Completed']:
        order.status = new_status
        log_order_status(order.id, new_status, commit=False)
        db.session.commit()
        buyer = User.query.get(order.buyer_id)
        if buyer and buyer.phone and new_status in ['Shipped', 'Delivered']:
            send_sms(buyer.phone, f'Update: Your Order #{order_id} has been {new_status}.')
        elif buyer and buyer.phone:
             # Generic update for other statuses
             send_sms(buyer.phone, f'Order #{order_id} status updated to {new_status}')
        return jsonify({'success': True, 'message': f'Order #{order_id} status updated to {new_status}.'})
    return jsonify({'success': False, 'error': 'Invalid status provided.'}), 400

@app.route('/admin/send_promotion', methods=['POST'])
@roles_required('admin')
def admin_send_promotion():
    data = request.get_json() or {}
    message = data.get('message')
    if not message:
        return jsonify({'success': False, 'error': 'No message provided'}), 400

    # Minimal implementation: log the message and pretend to send to users
    try:
        # In a real app: queue emails/notifications here
        print(f"[ADMIN PROMO] Message to users: {message}")
        return jsonify({'success': True, 'message': 'Promotion scheduled'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/export_report')
@roles_required('admin')
def admin_export_report():
    # Export basic orders report as CSV
    import io, csv
    orders = Order.query.order_by(Order.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['order_id', 'buyer_id', 'total_amount', 'status', 'created_at'])
    for o in orders:
        writer.writerow([o.id, o.buyer_id, o.total_amount, o.status, o.created_at.isoformat()])
    output.seek(0)
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='orders_report.csv')

@app.route('/admin/track_order/<int:order_id>')
@roles_required('admin')
def admin_track_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_items = OrderItem.query.filter_by(order_id=order.id).all()
    status_history = OrderStatusHistory.query.filter_by(order_id=order.id).order_by(OrderStatusHistory.timestamp.asc()).all()
    order_notes = OrderNote.query.filter_by(order_id=order.id).options(db.joinedload(OrderNote.author)).order_by(OrderNote.created_at.asc()).all()
    buyer = User.query.get(order.buyer_id)

    # Backfill initial status if it's missing for older orders
    if not status_history:
        log_order_status(order.id, order.status)
        status_history = OrderStatusHistory.query.filter_by(order_id=order.id).order_by(OrderStatusHistory.timestamp.asc()).all()

    # Combine and sort timeline events
    timeline_events = []
    for history in status_history:
        timeline_events.append({'type': 'status', 'data': history, 'timestamp': history.timestamp})
    for note in order_notes:
        timeline_events.append({'type': 'note', 'data': note, 'timestamp': note.created_at})
    
    timeline_events.sort(key=lambda x: x['timestamp'])

    return render_template('admin_track_order.html', 
                           order=order, 
                           order_items=order_items, 
                           timeline_events=timeline_events, 
                           buyer=buyer,
                           active_page='orders')

@app.route('/admin/add_order_note/<int:order_id>', methods=['POST'])
@roles_required('admin')
def add_order_note(order_id):
    order = Order.query.get_or_404(order_id)
    note_text = request.form.get('note_text')
    is_public = 'is_public' in request.form

    if not note_text or not note_text.strip():
        flash('Note cannot be empty.', 'error')
        return redirect(url_for('admin_track_order', order_id=order_id))
    
    new_note = OrderNote(order_id=order_id, author_id=session['user_id'], note_text=note_text, is_public=is_public)
    db.session.add(new_note)
    db.session.commit()
    flash('Note added successfully.', 'success')
    return redirect(url_for('admin_track_order', order_id=order_id))

@app.route('/admin/edit_order_note/<int:note_id>', methods=['POST'])
@roles_required('admin')
def edit_order_note(note_id):
    note = OrderNote.query.get_or_404(note_id)
    data = request.get_json()
    new_text = data.get('note_text')

    if not new_text or not new_text.strip():
        return jsonify({'success': False, 'error': 'Note text cannot be empty.'}), 400

    note.note_text = new_text
    db.session.commit()

    return jsonify({'success': True, 'message': 'Note updated successfully.'})

@app.route('/admin/delivery_persons')
@roles_required('admin')
def admin_delivery_persons():
    persons = DeliveryPerson.query.order_by(DeliveryPerson.name.asc()).all()
    return render_template('admin_delivery_persons.html', 
                           persons=persons, 
                           active_page='delivery_persons')

@app.route('/admin/delivery_person/add', methods=['POST'])
@roles_required('admin')
def add_delivery_person():
    data = request.form
    files = request.files
    # Basic validation
    if not all(k in data for k in ['name', 'phone', 'vehicle_number', 'license_number']):
        return jsonify({'success': False, 'error': 'Missing required fields.'}), 400

    # Check for uniqueness
    if DeliveryPerson.query.filter_by(phone=data['phone']).first():
        return jsonify({'success': False, 'error': 'Phone number already exists.'}), 400
    if DeliveryPerson.query.filter_by(vehicle_number=data['vehicle_number']).first():
        return jsonify({'success': False, 'error': 'Vehicle number already exists.'}), 400
    if DeliveryPerson.query.filter_by(license_number=data['license_number']).first():
        return jsonify({'success': False, 'error': 'License number already exists.'}), 400

    # Handle file uploads
    profile_pic_path = None
    if 'profile_picture' in files and files['profile_picture'].filename != '':
        file = files['profile_picture']
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'delivery_persons', unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)
        profile_pic_path = f"uploads/delivery_persons/{unique_filename}"

    license_image_path = None
    if 'license_image' in files and files['license_image'].filename != '':
        file = files['license_image']
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'delivery_persons', unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)
        license_image_path = f"uploads/delivery_persons/{unique_filename}"

    new_person = DeliveryPerson(
        name=data['name'],
        phone=data['phone'],
        address=data.get('address'),
        vehicle_type=data.get('vehicle_type', 'Bike'),
        vehicle_number=data['vehicle_number'],
        license_number=data['license_number'],
        is_active='is_active' in data,
        profile_picture=profile_pic_path,
        license_image=license_image_path
    )
    db.session.add(new_person)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Delivery person added successfully.'}), 201

@app.route('/admin/delivery_person/<int:person_id>')
@roles_required('admin')
def get_delivery_person(person_id):
    person = DeliveryPerson.query.get_or_404(person_id)
    return jsonify({
        'id': person.id,
        'name': person.name,
        'phone': person.phone,
        'address': person.address,
        'vehicle_type': person.vehicle_type,
        'vehicle_number': person.vehicle_number,
        'license_number': person.license_number,
        'is_active': person.is_active,
        'profile_picture': person.profile_picture,
        'license_image': person.license_image
    })

@app.route('/admin/delivery_person/edit/<int:person_id>', methods=['POST'])
@roles_required('admin')
def edit_delivery_person(person_id):
    person = DeliveryPerson.query.get_or_404(person_id)
    data = request.form
    files = request.files

    # Uniqueness checks (if changed)
    if 'phone' in data and data['phone'] != person.phone and DeliveryPerson.query.filter_by(phone=data['phone']).first():
        return jsonify({'success': False, 'error': 'Phone number already exists.'}), 400
    if 'vehicle_number' in data and data['vehicle_number'] != person.vehicle_number and DeliveryPerson.query.filter_by(vehicle_number=data['vehicle_number']).first():
        return jsonify({'success': False, 'error': 'Vehicle number already exists.'}), 400
    if 'license_number' in data and data['license_number'] != person.license_number and DeliveryPerson.query.filter_by(license_number=data['license_number']).first():
        return jsonify({'success': False, 'error': 'License number already exists.'}), 400

    person.name = data.get('name', person.name)
    person.phone = data.get('phone', person.phone)
    person.address = data.get('address', person.address)
    person.vehicle_type = data.get('vehicle_type', person.vehicle_type)
    person.vehicle_number = data.get('vehicle_number', person.vehicle_number)
    person.license_number = data.get('license_number', person.license_number)
    person.is_active = 'is_active' in data

    # Handle file uploads
    if 'profile_picture' in files and files['profile_picture'].filename != '':
        file = files['profile_picture']
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'delivery_persons', unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)
        person.profile_picture = f"uploads/delivery_persons/{unique_filename}"

    if 'license_image' in files and files['license_image'].filename != '':
        file = files['license_image']
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'delivery_persons', unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)
        person.license_image = f"uploads/delivery_persons/{unique_filename}"

    db.session.commit()
    return jsonify({'success': True, 'message': 'Details updated successfully.'})

@app.route('/admin/delivery_person/delete/<int:person_id>', methods=['POST'])
@roles_required('admin')
def delete_delivery_person(person_id):
    person = DeliveryPerson.query.get_or_404(person_id)
    db.session.delete(person)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Delivery person removed successfully.'})

@app.route('/admin/delivery_person/details/<int:person_id>')
@roles_required('admin')
def delivery_person_details(person_id):
    person = DeliveryPerson.query.get_or_404(person_id)
    
    # Fetch orders assigned to this person
    assigned_orders = db.session.query(
        Order, User.name.label('customer_name')
    ).join(User, Order.buyer_id == User.id)\
     .filter(Order.delivery_person_id == person_id)\
     .order_by(Order.created_at.desc()).all()

    # Calculate summary stats
    summary_stats = db.session.query(
        db.func.count(Order.id).label('total_deliveries'),
        db.func.sum(Order.delivery_fee).label('total_earnings')
    ).filter(
        Order.delivery_person_id == person_id,
        Order.status.in_(['Delivered', 'Completed'])
    ).first()

    return render_template('admin_delivery_person_details.html', 
                           person=person, 
                           assigned_orders=assigned_orders, 
                           total_deliveries=summary_stats.total_deliveries or 0,
                           total_earnings=summary_stats.total_earnings or 0.0,
                           active_page='delivery_persons')

@app.route('/admin/create_invoice')
@roles_required('admin')
def admin_create_invoice():
    # Minimal invoice generation: produce a simple text invoice for the latest order
    latest = Order.query.order_by(Order.created_at.desc()).first()
    if not latest:
        return jsonify({'success': False, 'error': 'No orders found'}), 404
    buyer = db.session.get(User, latest.buyer_id)
    invoice_text = [
        f"Invoice for Order #{latest.id}",
        f"Buyer: {buyer.name if buyer else 'Unknown'} ({buyer.email if buyer else 'N/A'})",
        f"Total: ₹{latest.total_amount}",
        f"Status: {latest.status}",
        f"Date: {latest.created_at.isoformat()}",
        "\nThank you for your purchase!"
    ]
    import io
    mem = io.BytesIO() 
    mem.write('\n'.join(invoice_text).encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/plain', as_attachment=True, download_name=f'invoice_{latest.id}.txt')


@app.route('/admin/order/<int:order_id>')
@roles_required('admin')
def admin_get_order(order_id):
    """Return basic order details as JSON for admin view."""
    order = db.session.get(Order, order_id)
    if not order:
        return {'error': 'Order not found'}, 404
    buyer = db.session.get(User, order.buyer_id)
    return {
        'id': order.id,
        'buyer': {'id': buyer.id, 'name': buyer.name, 'email': buyer.email} if buyer else None,
        'total_amount': order.total_amount,
        'payment_mode': order.payment_mode,
        'status': order.status,
        'created_at': order.created_at.isoformat()
    }


@app.route('/admin/low_stock')
@roles_required('admin')
def admin_low_stock():
    """Return low-stock products as JSON."""
    threshold = request.args.get('threshold', None)
    try:
        if threshold is not None:
            threshold = int(threshold)
        else:
            threshold = 5
    except ValueError:
        threshold = 5
    products = Product.query.filter(Product.quantity <= threshold).order_by(Product.quantity.asc()).all()
    data = [{'id': p.id, 'name': p.name, 'quantity': p.quantity, 'unit': p.unit} for p in products]
    return {'products': data, 'threshold': threshold, 'count': len(data)}, 200


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@roles_required('admin')
def admin_edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return {'error': 'User not found'}, 404
    if request.method == 'GET':
        return {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'phone': user.phone,
            'account_number': user.account_number,
            'upi_phone_number': user.upi_phone_number,
            'is_approved': user.is_approved
        }, 200

    # POST - update user fields (expects JSON body)
    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    role = data.get('role')
    phone = data.get('phone')
    account_number = data.get('account_number')
    upi_phone_number = data.get('upi_phone_number')
    try:
        if name:
            user.name = name
        if email:
            user.email = email
        if role:
            user.role = role
        if phone:
            user.phone = phone
        if account_number:
            user.account_number = account_number
        if upi_phone_number:
            user.upi_phone_number = upi_phone_number
        db.session.commit()
        return {'success': True, 'message': 'User updated'}, 200
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500

@app.route('/admin/payouts')
@roles_required('admin')
def admin_payouts():
    """View for managing seller payouts."""
    # Get all sellers
    sellers = User.query.filter(User.role.in_(['seller', 'farmer'])).all()
    payout_data = []
    
    for seller in sellers:
        # Calculate pending balance: Sum of items sold that are Delivered/Completed but not paid out
        pending_items_query = db.session.query(
            db.func.sum(OrderItem.price * OrderItem.quantity).label('gross_total'),
            db.func.sum(OrderItem.commission_amount).label('total_commission')
        ).join(Order, OrderItem.order_id == Order.id)\
         .filter(
             OrderItem.seller_id == seller.id,
             OrderItem.is_paid_to_seller == False,
             Order.status.in_(['Delivered', 'Completed'])
         ).first()
        
        gross_amount = pending_items_query.gross_total or 0
        total_commission = pending_items_query.total_commission or 0
        pending_amount = gross_amount - total_commission
         
        last_payout = Payout.query.filter_by(seller_id=seller.id).order_by(Payout.created_at.desc()).first()
        
        payout_data.append({
            'seller': seller,
            'pending_amount': pending_amount,
            'gross_amount': gross_amount,
            'total_commission': total_commission,
            'last_payout_date': last_payout.created_at if last_payout else None,
            'last_payout_amount': last_payout.amount if last_payout else 0
        })
    
    # Payout History
    payout_history = db.session.query(Payout, User.name).join(User, Payout.seller_id == User.id).order_by(Payout.created_at.desc()).all()
    
    # Add context for the layout
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()

    return render_template('admin_payouts.html', payout_data=payout_data, payout_history=payout_history, active_page='payouts', pending_orders_count=pending_orders_count, low_stock_count=low_stock_count)

@app.route('/admin/process_payout', methods=['POST'])
@roles_required('admin')
def admin_process_payout():
    seller_id = request.form.get('seller_id')
    transaction_ref = request.form.get('transaction_ref', 'CASH')
    
    # Get pending items to calculate commission and mark as paid
    pending_items = db.session.query(OrderItem).join(Order, OrderItem.order_id == Order.id)\
        .filter(
             OrderItem.seller_id == seller_id,
             OrderItem.is_paid_to_seller == False,
             Order.status.in_(['Delivered', 'Completed'])
         ).all()

    if not pending_items:
        flash('No pending items found for this seller.', 'info')
        return redirect(url_for('admin_payouts'))

    gross_amount = sum(item.price * item.quantity for item in pending_items)
    total_commission_for_payout = sum(item.commission_amount for item in pending_items)
    net_amount = gross_amount - total_commission_for_payout
         
    # Create Payout Record
    payout = Payout(seller_id=seller_id, amount=net_amount, transaction_ref=transaction_ref, commission_total=total_commission_for_payout)
    db.session.add(payout)
         
    for item in pending_items:
        item.is_paid_to_seller = True
        
    db.session.commit()
    
    # Notify Seller/Farmer about payout
    seller = db.session.get(User, seller_id)
    if seller:
        msg = f"Payout of Rs.{net_amount:.2f} processed. Ref: {transaction_ref}."
        if seller.phone:
            send_sms(seller.phone, msg)
        if seller.email:
            send_notification_email(seller.email, "Payout Processed", f"Dear {seller.name},\n\n{msg}\n\nThank you.")

    flash(f'Payout of ₹{net_amount:.2f} recorded successfully.', 'success')
    return redirect(url_for('admin_payouts'))

@app.route('/profile')
@roles_required('buyer', 'seller', 'admin', 'farmer')
def profile():
    """Displays the current user's profile page."""
    user = User.query.get_or_404(session['user_id'])
    return render_template('profile.html', user=user)

@app.route('/profile/edit', methods=['GET', 'POST'])
@roles_required('buyer', 'seller', 'admin', 'farmer')
def edit_profile():
    """Handles editing the user's profile information."""
    user = User.query.get_or_404(session['user_id'])

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        # Basic validation
        if not name or not email:
            flash('Name and email cannot be empty.', 'error')
            return render_template('edit_profile.html', user=user)

        # Check if email is being changed and if the new one is already taken
        if email != user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('That email address is already in use. Please choose another.', 'error')
                return render_template('edit_profile.html', user=user)
        
        # Update user details
        user.name = name
        user.email = email
        user.phone = phone
        db.session.commit()

        # Update session data to reflect the change immediately
        session['user_name'] = user.name

        flash('Your profile has been updated successfully!', 'success')
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# Static Pages
@app.route('/shipping_info')
def shipping_info():
    return render_template('shipping_info.html')

@app.route('/return_policy')
def return_policy():
    return render_template('return_policy.html')

@app.route('/faqs')
def faqs():
    return render_template('faqs.html')

@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms_and_conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html')

@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
@roles_required('buyer', 'seller', 'admin', 'farmer')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        if 'user_id' not in session or session['user_role'] != 'buyer':
            flash('Only buyers can submit reviews.', 'error')
            return redirect(url_for('product_detail', product_id=product_id))

        has_purchased = db.session.query(Order.id).join(OrderItem).filter(
            Order.buyer_id == session['user_id'],
            OrderItem.product_id == product_id,
            Order.status.in_(['Completed', 'Delivered'])
        ).first()

        if not has_purchased:
            flash('You can only review products you have purchased.', 'error')
            return redirect(url_for('product_detail', product_id=product_id))

        if ProductReview.query.filter_by(buyer_id=session['user_id'], product_id=product_id).first():
            flash('You have already reviewed this product.', 'info')
            return redirect(url_for('product_detail', product_id=product_id))

        rating = request.form.get('rating')
        review_text = request.form.get('review_text')

        if not rating:
            flash('Rating is required.', 'error')
            return redirect(url_for('product_detail', product_id=product_id))

        new_review = ProductReview(
            product_id=product_id,
            buyer_id=session['user_id'],
            rating=int(rating),
            review_text=review_text
        )
        db.session.add(new_review)
        db.session.commit()

        flash('Thank you for your review!', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    # GET request logic
    reviews_with_users = db.session.query(ProductReview, User.name).join(User, ProductReview.buyer_id == User.id).filter(ProductReview.product_id == product_id).order_by(ProductReview.created_at.desc()).all()
    avg_rating = db.session.query(db.func.avg(ProductReview.rating)).filter(ProductReview.product_id == product_id).scalar() or 0
    review_count = ProductReview.query.filter_by(product_id=product_id).count()
    
    can_review = False
    if 'user_id' in session and session['user_role'] == 'buyer':
        has_purchased = db.session.query(Order.id).join(OrderItem).filter(Order.buyer_id == session['user_id'], OrderItem.product_id == product_id, Order.status.in_(['Completed', 'Delivered'])).first() is not None
        has_reviewed = ProductReview.query.filter_by(buyer_id=session['user_id'], product_id=product_id).first() is not None
        if has_purchased and not has_reviewed:
            can_review = True

    return render_template('product_detail.html', product=product, reviews_with_users=reviews_with_users, avg_rating=avg_rating, review_count=review_count, can_review=can_review)

@app.route('/seller_dashboard')
@roles_required('seller', 'farmer')
def seller_dashboard():
    user_id = session['user_id']
    
    # --- Products ---
    products = Product.query.filter_by(seller_id=user_id).order_by(Product.created_at.desc()).all()
    
    # --- Sales Stats ---
    # Total lifetime earnings (gross)
    total_earnings = db.session.query(db.func.sum(OrderItem.price * OrderItem.quantity))\
        .filter(OrderItem.seller_id == user_id).scalar() or 0
    
    # Total items sold
    total_sold = db.session.query(db.func.sum(OrderItem.quantity))\
        .filter(OrderItem.seller_id == user_id).scalar() or 0

    # --- Pending Payout ---
    pending_items_query = db.session.query(
        db.func.sum(OrderItem.price * OrderItem.quantity).label('gross_total'),
        db.func.sum(OrderItem.commission_amount).label('total_commission')
    ).join(Order, OrderItem.order_id == Order.id)\
     .filter(
         OrderItem.seller_id == user_id,
         OrderItem.is_paid_to_seller == False,
         Order.status.in_(['Delivered', 'Completed'])
     ).first()
    
    gross_pending = pending_items_query.gross_total or 0
    commission_pending = pending_items_query.total_commission or 0
    pending_amount = gross_pending - commission_pending

    # --- Chart Data (last 7 days) ---
    today = datetime.now().date()
    sales_labels = []
    sales_values = []
    
    for i in range(7):
        day = today - timedelta(days=i)
        day_sales = db.session.query(db.func.sum(OrderItem.price * OrderItem.quantity))\
         .join(Order, OrderItem.order_id == Order.id)\
         .filter(OrderItem.seller_id == user_id)\
         .filter(db.func.date(Order.created_at) == day).scalar() or 0
        
        sales_labels.insert(0, day.strftime('%b %d'))
        sales_values.insert(0, day_sales)

    return render_template('seller_dashboard.html', 
                           active_page='dashboard',
                           products=products, 
                           total_earnings=total_earnings, 
                           total_sold=total_sold,
                           pending_amount=pending_amount,
                           sales_labels=sales_labels,
                           sales_values=sales_values)

@app.route('/seller/payouts')
@roles_required('seller', 'farmer')
def seller_payouts():
    user_id = session['user_id']
    
    # Payout History
    payout_history = Payout.query.filter_by(seller_id=user_id).order_by(Payout.created_at.desc()).all()
    
    return render_template('seller_payouts.html', 
                           active_page='payouts',
                           payout_history=payout_history)

@app.route('/seller/edit_product/<int:product_id>', methods=['GET', 'POST'])
@roles_required('seller', 'farmer')
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Ensure the product belongs to the current seller
    if product.seller_id != session['user_id']:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        flash('You are not authorized to edit this product.', 'error')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            product.name = data.get('name', product.name)
            product.category = data.get('category', product.category)
            product.price = float(data.get('price', product.price))
            product.quantity = int(data.get('quantity', product.quantity))
            product.unit = data.get('unit', product.unit)
            product.image = data.get('image', product.image)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Product updated successfully!'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    # GET request for modal
    return jsonify({
        'id': product.id,
        'name': product.name,
        'category': product.category,
        'price': product.price,
        'quantity': product.quantity,
        'unit': product.unit,
        'image': product.image or ''
    })

@app.route('/seller/delete_product/<int:product_id>', methods=['POST'])
@roles_required('seller', 'farmer')
def seller_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != session['user_id']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        product_name = product.name
        db.session.delete(product)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Product "{product_name}" deleted successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/payout_invoice/<int:payout_id>')
@roles_required('admin', 'seller', 'farmer')
def payout_invoice(payout_id):
    payout = Payout.query.get_or_404(payout_id)
    # Security check: Admin can see any, seller can only see their own.
    if session['user_role'] != 'admin' and payout.seller_id != session['user_id']:
        flash('You are not authorized to view this invoice.', 'error')
        return redirect(url_for('index'))
    
    seller = db.session.get(User, payout.seller_id)
    return render_template('payout_invoice.html', payout=payout, seller=seller)

if __name__ == '__main__':
    app.run(debug=True)