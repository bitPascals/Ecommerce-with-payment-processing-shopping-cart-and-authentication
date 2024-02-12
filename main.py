from functools import wraps
from flask import Flask, abort, render_template, flash, session
from flask_bootstrap import Bootstrap
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
# Additional imports for admin-only decorator
from flask import g, request, redirect, url_for
from datetime import datetime
import os

# Setting up the flask app
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

# Setting up login manager
login_manager = LoginManager(app)
login_manager.init_app(app)

# Setting up database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///users.db")
db = SQLAlchemy()
db.init_app(app)

# Creating the User model
class Users(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(250))
    last_name = db.Column(db.String(250))
    email = db.Column(db.String(250), unique=True)
    password = db.Column(db.String(250))


# Creating the product model
class Product(db.Model):
    __tablename__ = "product"
    id = db.Column(db.Integer, primary_key=True)
    p_name = db.Column(db.String(250), nullable=False)
    p_price = db.Column(db.Integer, nullable=False)
    p_image = db.Column(db.String(250), nullable=False)
    p_description = db.Column(db.String(250), nullable=False)
    p_type = db.Column(db.String(250), nullable=False)
    cart_items = relationship("CartItems", back_populates="product")


# Creating the cart model
class CartItems(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = relationship("Product")


# Setting up a user_loader callback for a user session
@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(Users, user_id)


with app.app_context():
    db.create_all()


# Create admin-only decorator
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If id is not 1, return abort with 403 error
        if current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return f(*args, **kwargs)
    return decorated_function


# Route home page
@app.route("/")
def home():
    result = db.session.execute(db.select(Product).order_by(Product.p_name))
    all_products = result.scalars().all()
    current_year = datetime.now().year
    result_ = db.session.execute(db.select(CartItems).order_by(CartItems.product_id))
    all_cart_items = result_.scalars().all()
    length = len(all_cart_items)
    return render_template("index.html", cart_length=length, year=current_year, products=all_products,
                           logged_in=current_user.is_authenticated)


# Route controls sign up functionality
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        hashed_password = generate_password_hash(
            request.form["password"], method='pbkdf2:sha256',
            salt_length=8
        )

        if password != confirm_password:
            flash("Your passwords match.")
            return redirect(url_for('signup'))
        else:
            new_user = Users(
                first_name=request.form["first_name"],
                last_name=request.form["last_name"],
                email=request.form["email"],
                password=hashed_password
             )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("home"))
    return render_template("signup.html", logged_in=current_user.is_authenticated)


# Route manages user loader
@login_manager.user_loader
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["email"] = request.form["email"]
        email = request.form["email"]
        password = request.form["password"]
        result = db.session.execute(db.select(Users).where(Users.email == email))
        user = result.scalar()

        if not user:
            flash("This email has not been registered. Please try again")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash("You have entered the wrong password. Please Try again")
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for("home"))
    return render_template("login.html", logged_in=current_user.is_authenticated)


# Setting up user loader callback for a user session
@login_manager.user_loader
def load_user(user_id):
    return Users.query.filter(Users.id == user_id).first()


# Adding products as with admin permission to the database
@app.route("/add_product", methods=["GET", "POST"])
@admin_only
def add_product():
    if request.method == "POST":
        new_product = Product(
            p_name=request.form["p_name"],
            p_price=request.form["p_price"],
            p_image=request.form["p_image"],
            p_description=request.form["p_description"],
            p_type=request.form["p_type"],
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product has been added successfully!")
    return render_template("add_product.html")


# Route displays cart items/products
@app.route("/my_cart")
def cart():
    cart_total = []
    if not current_user.is_authenticated:
        return redirect("login")
    cart_items = CartItems.query.all()
    result = db.session.execute(db.select(CartItems).order_by(CartItems.product_id))
    all_cart_items = result.scalars().all()
    for item in all_cart_items:
        total = item.quantity * item.product.p_price
        cart_total.append(total)
    total_sum = sum(cart_total)
    length = len(all_cart_items)
    return render_template("cart.html", cart_length=length, cart_items=cart_items, total_sum=total_sum,
                           logged_in=current_user.is_authenticated)


# Route app products to the cart
@app.route("/add_to_cart/<int:product_id>", methods=["GET", "POST"])
def add_to_cart(product_id):
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    product = Product.query.filter(Product.id == product_id).first()
    cart_item = CartItems(product=product)
    result = db.session.execute(db.select(CartItems).order_by(CartItems.product_id))
    all_cart_items = result.scalars().all()
    for item in all_cart_items:
        if cart_item.product.id == item.product_id:
            flash("Product already exists in your cart!")
            return redirect(url_for("home"))
    db.session.add(cart_item)
    db.session.commit()
    flash("Product has been added to your cart!")
    return redirect(url_for("home"))


# Route removes items from cart
@app.route("/delete_from_cart/<int:cart_id>")
def delete_from_cart(cart_id):
    cart_item = db.get_or_404(CartItems, cart_id)
    db.session.delete(cart_item)
    db.session.commit()
    return redirect(url_for("cart"))


# Route updates cart in quantity and price tag
@app.route("/update_cart/<int:cart_id>", methods=["GET", "POST"])
def update_cart(cart_id):
    cart_item = db.get_or_404(CartItems, cart_id)
    if request.method == "POST":
        cart_item.quantity = request.form.get('quantity', type=int)
        if cart_item.quantity < 1:
            cart_item.quantity = 1
        db.session.commit()
        return redirect(url_for('cart'))
    return render_template("cart.html", logged_in=current_user.is_authenticated)


# Route logs out user session
@app.route('/logout')
def logout():
    logout_user()
    session["email"] = None
    return redirect(url_for('home'))


# Route checks out to payment gateway
@app.route("/checkout")
def checkout():
    cart_total = []
    result = db.session.execute(db.select(CartItems).order_by(CartItems.product_id))
    all_cart_items = result.scalars().all()
    for item in all_cart_items:
        total = item.quantity * item.product.p_price
        cart_total.append(total)
    total_sum = sum(cart_total)
    return render_template("checkout.html", total=total_sum)


if __name__ == "__main__":
    app.run(debug=False)
