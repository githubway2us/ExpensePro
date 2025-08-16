import os
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
import logging

# ------------------- CONFIG -------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.getenv('EXPENSE_DB', 'expensepro.db')}"
app.config['JWT_SECRET_KEY'] = os.getenv('FLASK_SECRET', 'changeme-secure-this-in-production')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})
jwt = JWTManager(app)

# ------------------- MODELS -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat()
        }

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), default="expense")  # expense/income
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "type": self.type,
            "created_at": self.created_at.isoformat()
        }

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    merchant = db.Column(db.String(120))
    account = db.Column(db.String(120))
    project = db.Column(db.String(120))
    tags = db.Column(db.String(255))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "amount": self.amount,
            "date": self.date.isoformat(),
            "merchant": self.merchant,
            "account": self.account,
            "project": self.project,
            "tags": self.tags,
            "note": self.note,
            "created_at": self.created_at.isoformat()
        }

with app.app_context():
    db.create_all()

# ------------------- HELPERS -------------------
def create_default_categories(user_id: int) -> None:
    """Create default categories for a new user."""
    defaults = [
        {"name": "อาหาร", "type": "expense"},
        {"name": "เดินทาง", "type": "expense"},
        {"name": "ที่พัก", "type": "expense"},
        {"name": "ลงทุน", "type": "expense"},
        {"name": "จิปาถะ", "type": "expense"},
        {"name": "อื่นๆ", "type": "expense"},
        {"name": "ขายดอกไม้", "type": "income"},
        {"name": "เงินพิเศษ", "type": "income"}
    ]
    try:
        for cat in defaults:
            if not Category.query.filter_by(user_id=user_id, name=cat["name"]).first():
                db.session.add(Category(user_id=user_id, **cat))
        db.session.commit()
        logger.info(f"Created default categories for user {user_id}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create default categories for user {user_id}: {str(e)}")

def validate_date(date_str: str) -> Optional[datetime.date]:
    """Validate and parse date string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

def validate_required_fields(data: Dict, fields: List[str]) -> Tuple[bool, str]:
    """Validate required fields in request data."""
    for field in fields:
        if field not in data or data[field] is None:
            return False, f"Missing required field: {field}"
    return True, ""

# ------------------- AUTH -------------------
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        is_valid, msg = validate_required_fields(data, ['username', 'password', 'email'])
        if not is_valid:
            return jsonify({"msg": msg}), 400

        if User.query.filter_by(username=data['username']).first():
            return jsonify({"msg": "Username already exists"}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({"msg": "Email already exists"}), 400

        hashed_pw = generate_password_hash(data['password'])
        user = User(username=data['username'], password_hash=hashed_pw, email=data['email'])
        db.session.add(user)
        db.session.commit()
        create_default_categories(user.id)
        logger.info(f"User registered: {data['username']}")
        return jsonify({"msg": "Registered successfully"}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "Database error occurred"}), 400
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ในไฟล์ backend (ส่วน /api/login)
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        is_valid, msg = validate_required_fields(data, ['username', 'password'])
        if not is_valid:
            return jsonify({"msg": msg}), 400

        user = User.query.filter_by(username=data['username']).first()
        if not user or not check_password_hash(user.password_hash, data['password']):
            return jsonify({"msg": "Invalid credentials"}), 401

        # แปลง user.id เป็น string
        token = create_access_token(identity=str(user.id))
        logger.info(f"User logged in: {data['username']}")
        return jsonify({"access_token": token, "user_id": user.id}), 200
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    try:
        uid = get_jwt_identity()
        user = User.query.get_or_404(uid)
        return jsonify(user.to_dict()), 200
    except Exception as e:
        logger.error(f"Profile fetch error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ------------------- CATEGORY -------------------
@app.route('/api/categories', methods=['GET', 'POST'])
@jwt_required()
def categories():
    try:
        uid = get_jwt_identity()
        if request.method == 'POST':
            data = request.json
            is_valid, msg = validate_required_fields(data, ['name'])
            if not is_valid:
                return jsonify({"msg": msg}), 400

            cat = Category(user_id=uid, name=data['name'], type=data.get('type', 'expense'))
            db.session.add(cat)
            db.session.commit()
            logger.info(f"Category added for user {uid}: {data['name']}")
            return jsonify({"msg": "Category added", "id": cat.id}), 201

        cats = Category.query.filter_by(user_id=uid).all()
        return jsonify([c.to_dict() for c in cats]), 200
    except Exception as e:
        logger.error(f"Category error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

@app.route('/api/categories/<int:cid>', methods=['PATCH', 'DELETE'])
@jwt_required()
def edit_category(cid):
    try:
        uid = get_jwt_identity()
        cat = Category.query.filter_by(id=cid, user_id=uid).first_or_404()

        if request.method == 'PATCH':
            data = request.json
            if 'name' in data:
                cat.name = data['name']
            if 'type' in data and data['type'] in ['expense', 'income']:
                cat.type = data['type']
            db.session.commit()
            logger.info(f"Category updated: {cid}")
            return jsonify({"msg": "Category updated"}), 200

        db.session.delete(cat)
        db.session.commit()
        logger.info(f"Category deleted: {cid}")
        return jsonify({"msg": "Category deleted"}), 200
    except Exception as e:
        logger.error(f"Category edit/delete error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ------------------- EXPENSE -------------------
@app.route('/api/expenses', methods=['GET', 'POST'])
@jwt_required()
def expenses():
    try:
        uid = get_jwt_identity()
        if request.method == 'POST':
            data = request.json
            is_valid, msg = validate_required_fields(data, ['category_id', 'amount', 'date'])
            if not is_valid:
                return jsonify({"msg": msg}), 400

            date_obj = validate_date(data['date'])
            if not date_obj:
                return jsonify({"msg": "Invalid date format"}), 400

            if not Category.query.filter_by(id=data['category_id'], user_id=uid).first():
                return jsonify({"msg": "Invalid category"}), 400

            exp = Expense(
                user_id=uid,
                category_id=data['category_id'],
                amount=float(data['amount']),
                date=date_obj,
                merchant=data.get('merchant'),
                account=data.get('account'),
                project=data.get('project'),
                tags=data.get('tags'),
                note=data.get('note')
            )
            db.session.add(exp)
            db.session.commit()
            logger.info(f"Expense added for user {uid}")
            return jsonify({"msg": "Expense added", "id": exp.id}), 201

        query = Expense.query.filter_by(user_id=uid)
        if 'from' in request.args:
            date_obj = validate_date(request.args['from'])
            if not date_obj:
                return jsonify({"msg": "Invalid from date format"}), 400
            query = query.filter(Expense.date >= date_obj)
        if 'to' in request.args:
            date_obj = validate_date(request.args['to'])
            if not date_obj:
                return jsonify({"msg": "Invalid to date format"}), 400
            query = query.filter(Expense.date <= date_obj)

        expenses = query.order_by(Expense.date.desc()).all()
        return jsonify([e.to_dict() for e in expenses]), 200
    except Exception as e:
        logger.error(f"Expense error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

@app.route('/api/expenses/<int:eid>', methods=['PATCH', 'DELETE'])
@jwt_required()
def edit_expense(eid):
    try:
        uid = get_jwt_identity()
        exp = Expense.query.filter_by(id=eid, user_id=uid).first_or_404()

        if request.method == 'PATCH':
            data = request.json
            for field in ['category_id', 'amount', 'merchant', 'account', 'project', 'tags', 'note']:
                if field in data:
                    setattr(exp, field, data[field])
            if 'date' in data:
                date_obj = validate_date(data['date'])
                if not date_obj:
                    return jsonify({"msg": "Invalid date format"}), 400
                exp.date = date_obj
            db.session.commit()
            logger.info(f"Expense updated: {eid}")
            return jsonify({"msg": "Expense updated"}), 200

        db.session.delete(exp)
        db.session.commit()
        logger.info(f"Expense deleted: {eid}")
        return jsonify({"msg": "Expense deleted"}), 200
    except Exception as e:
        logger.error(f"Expense edit/delete error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ------------------- IMPORT / EXPORT -------------------
@app.route('/api/import', methods=['POST'])
@jwt_required()
def import_csv():
    try:
        uid = get_jwt_identity()
        if 'file' not in request.files:
            return jsonify({"msg": "No file uploaded"}), 400

        file = request.files['file']
        if not file.filename.endswith('.csv'):
            return jsonify({"msg": "File must be CSV"}), 400

        reader = csv.DictReader(io.StringIO(file.stream.read().decode()))
        required_fields = ['category', 'amount', 'date']
        for row in reader:
            is_valid, msg = validate_required_fields(row, required_fields)
            if not is_valid:
                return jsonify({"msg": f"Invalid row data: {msg}"}), 400

            date_obj = validate_date(row['date'])
            if not date_obj:
                return jsonify({"msg": f"Invalid date in row: {row['date']}"}), 400

            cat = Category.query.filter_by(user_id=uid, name=row['category']).first()
            if not cat:
                cat = Category(user_id=uid, name=row['category'], type=row.get('type', 'expense'))
                db.session.add(cat)
                db.session.commit()

            exp = Expense(
                user_id=uid,
                category_id=cat.id,
                amount=float(row['amount']),
                date=date_obj,
                merchant=row.get('merchant'),
                account=row.get('account'),
                project=row.get('project'),
                tags=row.get('tags'),
                note=row.get('note')
            )
            db.session.add(exp)
        db.session.commit()
        logger.info(f"CSV imported for user {uid}")
        return jsonify({"msg": "Import completed"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"CSV import error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

@app.route('/api/export', methods=['GET'])
@jwt_required()
def export_csv():
    try:
        uid = get_jwt_identity()
        query = Expense.query.filter_by(user_id=uid)
        if 'from' in request.args:
            date_obj = validate_date(request.args['from'])
            if not date_obj:
                return jsonify({"msg": "Invalid from date format"}), 400
            query = query.filter(Expense.date >= date_obj)
        if 'to' in request.args:
            date_obj = validate_date(request.args['to'])
            if not date_obj:
                return jsonify({"msg": "Invalid to date format"}), 400
            query = query.filter(Expense.date <= date_obj)

        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')  # ใช้ lineterminator=\n สำหรับความเข้ากันได้
        writer.writerow(["date", "amount", "category", "merchant", "account", "project", "tags", "note"])
        for e in query.all():
            cat = Category.query.get(e.category_id)
            writer.writerow([
                e.date.isoformat(),
                e.amount,
                cat.name if cat else "Unknown",
                e.merchant or "",
                e.account or "",
                e.project or "",
                e.tags or "",
                e.note or ""
            ])
        output.seek(0)
        filename = f"expenses_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        logger.info(f"CSV exported for user {uid}")
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),  # Encode เป็น UTF-8
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except JWTDecodeError:
        logger.error("Invalid JWT token")
        return jsonify({"msg": "Invalid or expired token"}), 401
    except Exception as e:
        logger.error(f"CSV export error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ------------------- SUMMARY -------------------
@app.route('/api/summary', methods=['GET'])
@jwt_required()
def summary():
    try:
        uid = get_jwt_identity()
        today = datetime.utcnow().date()
        month_start = today.replace(day=1)

        total_expense = db.session.query(db.func.sum(Expense.amount))\
            .join(Category)\
            .filter(
                Expense.user_id == uid,
                Category.type == 'expense',
                Expense.date >= month_start
            ).scalar() or 0

        total_income = db.session.query(db.func.sum(Expense.amount))\
            .join(Category)\
            .filter(
                Expense.user_id == uid,
                Category.type == 'income',
                Expense.date >= month_start
            ).scalar() or 0

        return jsonify({
            "total_expense": float(total_expense),
            "total_income": float(total_income),
            "balance": float(total_income - total_expense)
        }), 200
    except Exception as e:
        logger.error(f"Summary error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

# ------------------- ANALYSIS -------------------
@app.route('/api/analysis', methods=['GET'])
@jwt_required()
def analysis():
    try:
        uid = get_jwt_identity()
        group_by = request.args.get('group_by', 'category_id')
        from_date = request.args.get('from')
        to_date = request.args.get('to')
        only_expense = request.args.get('only_expense') == '1'

        if group_by not in ['category_id', 'merchant', 'account', 'project']:
            return jsonify({"msg": "Invalid group_by parameter"}), 400

        query = db.session.query(getattr(Expense, group_by), db.func.sum(Expense.amount))\
            .join(Category)\
            .filter(Expense.user_id == uid)

        if only_expense:
            query = query.filter(Category.type == 'expense')
        if from_date:
            date_obj = validate_date(from_date)
            if not date_obj:
                return jsonify({"msg": "Invalid from date format"}), 400
            query = query.filter(Expense.date >= date_obj)
        if to_date:
            date_obj = validate_date(to_date)
            if not date_obj:
                return jsonify({"msg": "Invalid to date format"}), 400
            query = query.filter(Expense.date <= date_obj)

        results = query.group_by(getattr(Expense, group_by)).all()
        return jsonify([{"group": r[0], "total": float(r[1])} for r in results]), 200
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return jsonify({"msg": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=os.getenv('FLASK_ENV') == 'development')