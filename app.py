from __future__ import annotations
# app.py

from bson.objectid import ObjectId
import os
import re
import uuid

def get_user_fields():
    """Debug function to check available fields in user documents"""
    sample_user = app.db.users.find_one({"role": "customer"})
    sample_pharmacy = app.db.pharmacies.find_one()
    print("Sample user fields:", list(sample_user.keys()) if sample_user else None)
    print("Sample pharmacy fields:", list(sample_pharmacy.keys()) if sample_pharmacy else None)
    return sample_user, sample_pharmacy
from datetime import datetime, timedelta
from functools import wraps

from bson import ObjectId

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        
        user_data = session.get('user', {})
        if user_data.get('role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('home'))
            
        return f(*args, **kwargs)
    return decorated_function
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import hashlib


# App & Database Configuration

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "images", "medicines")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  
    app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
    
    # Create upload directory if it doesn't exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/medpanda")
    client = MongoClient(mongo_uri)
    
    # Explicitly use the medpanda database
    app.db = client.medpanda

    # Ensure indexes and create default admin user
    ensure_indexes(app.db)
    create_default_admin(app.db)

    # Small helper: attach current_user to g-like property
    @app.before_request
    def inject_user():
        
        app.current_user = session.get("user")  # dict or None
    
    @app.context_processor
    def inject_user_into_templates():
        return {'user': session.get('user')}
    # -----------------------------
    # Auth & Role Decorators
    # -----------------------------
    def login_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("user"):
                flash("Please log in first.", "warning")
                return redirect(url_for("login", next=request.path))
            return f(*args, **kwargs)
        return wrapper

    def roles_required(*roles):
        def deco(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                user = session.get("user")
                if not user:
                    flash("Please log in first.", "warning")
                    return redirect(url_for("login", next=request.path))
                if user.get("role") not in roles:
                    abort(403)
                return f(*args, **kwargs)
            return wrapper
        return deco

    # -------------
    # Basic Pages
    # -------------
    @app.route("/")
    def index():
        # Show featured medicines & quick search bar
        meds = list(app.db.medicines.find({"is_active": True}).sort("created_at", DESCENDING).limit(8))
        pharmacies = list(app.db.pharmacies.find({"is_active": True}, {"name": 1}))
        return render_template("index.html", meds=meds, pharmacies=pharmacies, user=session.get("user"))

    # -------------
    # Auth
    # -------------
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "user")  # user | pharmacy | delivery
            
            # Prevent creating new admin users through registration
            if role == "admin":
                flash("Admin accounts cannot be created through registration.", "danger")
                return redirect(url_for("register"))
                
            if not name or not email or not password or not role:
                flash("All fields are required.", "danger")
                return redirect(url_for("register"))

            if app.db.users.find_one({"email": email}):
                flash("Email already registered.", "warning")
                return redirect(url_for("register"))

            hashed = generate_password_hash(password)
            user_doc = {
                "name": name,
                "email": email,
                "password": hashed,
                "role": role if role in {"user", "pharmacy", "delivery"} else "user",
                "created_at": datetime.utcnow(),
                "is_active": True,
            }
            res = app.db.users.insert_one(user_doc)

            # If pharmacy role, create pharmacy stub
            if user_doc["role"] == "pharmacy":
                app.db.pharmacies.insert_one({
                    "owner_id": res.inserted_id,
                    "name": f"{name}'s Pharmacy",
                    "address": "",
                    "phone": "",
                    "is_active": True,
                    "rating_avg": 0.0,
                    "rating_count": 0,
                    "created_at": datetime.utcnow(),
                })

            # If delivery role, create delivery profile
            if user_doc["role"] == "delivery":
                app.db.delivery_profiles.insert_one({
                    "user_id": res.inserted_id,
                    "vehicle_type": request.form.get("vehicle_type", "Bike"),
                    "phone": request.form.get("phone", ""),
                    "license_number": request.form.get("license_number", ""),
                    "is_available": True,
                    "current_location": "",
                    "rating_avg": 0.0,
                    "rating_count": 0,
                    "created_at": datetime.utcnow(),
                })

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        
        # GET request - show registration form with role options
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = app.db.users.find_one({"email": email, "is_active": True})
            if not user or not check_password_hash(user["password"], password):
                flash("Invalid credentials.", "danger")
                return redirect(url_for("login"))

            # Minimal session payload
            session["user"] = {
                "_id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            }
            flash(f"Welcome, {user['name']}!", "success")
            
            # Redirect based on user role
            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            elif user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "pharmacy":
                return redirect(url_for("pharmacy_dashboard"))
            elif user["role"] == "delivery":
                return redirect(url_for("delivery_dashboard"))
            elif user["role"] == "user":
                return redirect(url_for("user_dashboard"))
            else:
                return redirect(url_for("index"))
                
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.pop("user", None)
        flash("Logged out.", "info")
        return redirect(url_for("index"))

    # ----------------------
    # User Dashboard
    # ----------------------
    @app.route("/user/dashboard")
    @roles_required("user", "admin")
    def user_dashboard():
        user = session.get("user")
        if user["role"] == "admin":
            # For admin, show the first regular user's data
            regular_user = app.db.users.find_one({"role": "user"})
            if not regular_user:
                flash("No regular users found in the system.", "warning")
                return redirect(url_for("admin_dashboard"))
            user_id = regular_user["_id"]
        else:
            # For regular user
            user_id = ObjectId(user["_id"])
        
        # Get orders and ensure items are properly handled
        orders_cursor = app.db.orders.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(10)
        orders = []
        
        for order in orders_cursor:
            # Convert BSON document to dict
            order = dict(order)
            
            # Handle items field consistently
            items = []
            if isinstance(order.get('items'), list):
                items = order['items']
            elif isinstance(order.get('order_items'), list):
                # Migrate old format to new
                items = order['order_items']
                order['items'] = items  # Add the new field
            
            order['items'] = items  # Ensure the items field exists
            orders.append(order)
        
        # Get schedules
        schedules_cursor = app.db.schedules.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(5)
        schedules = list(schedules_cursor)
        
        return render_template("user_dashboard.html", orders=orders, schedules=schedules)
    

    # ----------------------
    # Delivery View
    # ----------------------
    @app.route("/delivery/view")
    @roles_required("admin")
    def delivery_view():
        # Get all delivery personnel from the database
        delivery_personnel = list(app.db.users.find({"role": "delivery"}))
        
        # Calculate ratings for each delivery person
        for delivery in delivery_personnel:
            # Get all reviews for this delivery person
            reviews = list(app.db.reviews.find({
                "delivery_person_id": str(delivery["_id"]),
                "type": "delivery"
            }))
            
            # Calculate average rating and review count
            if reviews:
                total_rating = sum(review["rating"] for review in reviews)
                delivery["avg_rating"] = total_rating / len(reviews)
                delivery["review_count"] = len(reviews)
            else:
                delivery["avg_rating"] = 0
                delivery["review_count"] = 0
                
        return render_template("delivery_view.html", delivery_personnel=delivery_personnel)

    @app.route("/delivery/view/<delivery_id>")
    @roles_required("admin")
    def view_delivery_details(delivery_id):
        # Get delivery personnel details from database
        delivery = app.db.users.find_one({"_id": ObjectId(delivery_id), "role": "delivery"})
        if not delivery:
            flash("Delivery personnel not found", "error")
            return redirect(url_for("delivery_view"))
            
        # Get assigned orders for this delivery personnel
        assigned_orders = list(app.db.orders.find({"delivery_id": ObjectId(delivery_id)}))
        
        return render_template(
            "delivery_details.html", 
            delivery=delivery,
            assigned_orders=assigned_orders
        )

    # ----------------------
    # Complaints Management
    # ----------------------
    @app.route("/complain", methods=["GET"])
    @login_required
    def complain():
        user = session.get("user")
        if user["role"] == "admin":
            # For admin, show all complaints
            complaints = list(app.db.complaints.find().sort("created_at", DESCENDING))
            # Fetch related user info for each complaint
            for complaint in complaints:
                complainant = app.db.users.find_one({"_id": complaint["complainant_id"]})
                complaint["complainant_name"] = complainant["name"] if complainant else "Unknown User"
                # No longer using against_id, just show role as label
                complaint["against_name"] = complaint["against_role"].capitalize()
                complaint["created_at_formatted"] = complaint["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            return render_template("admin_complaints.html", complaints=complaints)
        else:
            # For regular users, show the complaint form
            return render_template("complain.html")

    @app.route("/submit_complain", methods=["POST"])
    @login_required
    def submit_complain():
        subject = request.form.get("subject")
        against_role = request.form.get("against_role")
        description = request.form.get("description")
        
        if not all([subject, against_role, description]):
            flash("All fields are required", "error")
            return redirect(url_for("complain"))
        
        # Create complaint document
        complaint = {
            "subject": subject,
            "against_role": against_role,
            "description": description,
            "complainant_id": ObjectId(session["user"]["_id"]),
            "complainant_role": session["user"]["role"],
            "status": "pending",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # Insert into database
        app.db.complaints.insert_one(complaint)
        flash("Your complaint has been submitted successfully", "success")
        return redirect(url_for("complain"))

    @app.route("/get_users_by_role/<role>")
    @login_required
    def get_users_by_role(role):
        print(f"Fetching users for role: {role}")  # Debug log
        
        # First, let's check what fields we have in our documents
        sample_user, sample_pharmacy = get_user_fields()
        
        users = []
        if role == "pharmacy":
            # Get all pharmacies
            pharmacies = list(app.db.pharmacies.find())
            print(f"Found {len(pharmacies)} pharmacies")
            for p in pharmacies:
                # Check what name field is actually available
                name = p.get('business_name') or p.get('name') or p.get('pharmacy_name', 'Unknown Pharmacy')
                users.append({
                    "_id": str(p["_id"]),
                    "name": name,
                    "role": "pharmacy"
                })
        elif role == "delivery":
            # Get delivery personnel
            delivery_users = list(app.db.users.find({"role": "delivery"}))
            print(f"Found {len(delivery_users)} delivery personnel")
            for u in delivery_users:
                name = u.get('username') or u.get('name', 'Unknown')
                email = u.get('email', 'No email')
                users.append({
                    "_id": str(u["_id"]),
                    "name": f"{name} ({email})",
                    "role": "delivery"
                })
        elif role == "customer":
            # Get customers
            customers = list(app.db.users.find({"role": "customer"}))
            print(f"Found {len(customers)} customers")
            for u in customers:
                name = u.get('username') or u.get('name', 'Unknown')
                email = u.get('email', 'No email')
                users.append({
                    "_id": str(u["_id"]),
                    "name": f"{name} ({email})",
                    "role": "customer"
                })
        elif role == "other":
            # Get all other users (excluding admin)
            other_users = list(app.db.users.find(
                {"role": {"$nin": ["admin"]}}, 
                {"_id": 1, "name": 1, "email": 1, "role": 1}
            ))
            users = [{
                "_id": str(u["_id"]),
                "name": f"{u['name']} ({u['role']} - {u['email']})",
                "role": u["role"]
            } for u in other_users]
        
        print(f"Returning {len(users)} users")  # Debug log
        print("Sample user data:", users[0] if users else "No users found")  # Debug log
        return jsonify(users)

    @app.route("/admin/complaints")
    @admin_required
    def admin_complaints():
        print("Session data:", session.get('user'))  # Debug log
        # Get all complaints from the database
        complaints = list(app.db.complaints.find().sort("created_at", DESCENDING))
        
        # Process complaints to include user details
        for complaint in complaints:
            complaint["_id"] = str(complaint["_id"])
            # Get complainant details
            if "complainant_id" in complaint:
                complainant = app.db.users.find_one({"_id": ObjectId(complaint["complainant_id"])})
                if complainant:
                    complaint["complainant_name"] = complainant["name"]
                    complaint["complainant_role"] = complainant["role"]
            # Get against details if it's a user
            if "against_id" in complaint:
                against = app.db.users.find_one({"_id": ObjectId(complaint["against_id"])})
                if against:
                    complaint["against_name"] = against["name"]
        
        return render_template("admin_complaints.html", complaints=complaints)

    @app.route("/admin/complaints/<complaint_id>", methods=["GET", "POST"])
    @admin_required
    def complaint_details(complaint_id):
            
        try:
            # Find the complaint
            complaint = app.db.complaints.find_one({"_id": ObjectId(complaint_id)})
            if not complaint:
                flash("Complaint not found", "error")
                return redirect(url_for("admin_complaints"))
            
            # Handle POST request (status update or admin notes)
            if request.method == "POST":
                if "status" in request.form:
                    new_status = request.form["status"]
                    if new_status in ["pending", "investigating", "resolved", "dismissed"]:
                        app.db.complaints.update_one(
                            {"_id": ObjectId(complaint_id)},
                            {"$set": {
                                "status": new_status,
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        flash("Status updated successfully", "success")
                
                if "admin_notes" in request.form:
                    app.db.complaints.update_one(
                        {"_id": ObjectId(complaint_id)},
                        {"$set": {
                            "admin_notes": request.form["admin_notes"],
                            "updated_at": datetime.utcnow()
                        }}
                    )
                    flash("Admin notes updated successfully", "success")
                
                # Refresh complaint data after updates
                complaint = app.db.complaints.find_one({"_id": ObjectId(complaint_id)})
            
            # Get complainant details
            complainant = app.db.users.find_one({"_id": ObjectId(complaint["complainant_id"])}) if "complainant_id" in complaint else None
            
            # Get details of the person/entity complaint is against
            against_user = None
            if "against_id" in complaint:
                against_user = app.db.users.find_one({"_id": ObjectId(complaint["against_id"])})
            
            # Prepare template data
            complaint_data = {
                "_id": complaint["_id"],
                "subject": complaint.get("subject", ""),
                "description": complaint.get("description", ""),
                "status": complaint.get("status", "pending"),
                "created_at": complaint["created_at"],
                "complainant_name": complainant["name"] if complainant else "Unknown",
                "complainant_role": complainant["role"] if complainant else "Unknown",
                "against_name": against_user["name"] if against_user else complaint.get("against_name", "Not specified"),
                "admin_notes": complaint.get("admin_notes", "")
            }
            
            print(f"Rendering complaint details for complaint ID: {complaint_id}")  # Debug log
            print(f"Complaint data: {complaint_data}")  # Debug log
            return render_template("complaint_details.html", complaint=complaint_data)
            
        except Exception as e:
            print(f"Error in complaint_details: {str(e)}")  # Debug log
            flash("Error loading complaint details", "error")
            return redirect(url_for("admin_complaints"))

    @app.route("/update_complaint_status/<complaint_id>", methods=["POST"])
    @roles_required("admin")
    def update_complaint_status(complaint_id):
        try:
            data = request.json
            status = data.get("status")
            if not status or status not in ["pending", "investigating", "resolved", "dismissed"]:
                return jsonify({"error": "Invalid status"}), 400
            
            update_data = {
                "status": status,
                "admin_notes": data.get("admin_notes"),
                "updated_at": datetime.utcnow()
            }
            
            result = app.db.complaints.update_one(
                {"_id": ObjectId(complaint_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                return jsonify({"success": True, "message": "Complaint updated successfully"})
            else:
                return jsonify({"success": False, "message": "No changes made to complaint"}), 400
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    # ----------------------
    # Delivery Dashboard (with profile editing)
    # ----------------------
    @app.route("/delivery/dashboard", methods=["GET", "POST"])
    @app.route("/delivery/dashboard/<delivery_id>", methods=["GET", "POST"])
    @roles_required("delivery", "admin")
    def delivery_dashboard(delivery_id=None):
        user = session.get("user")
        is_admin = user["role"] == "admin"

        if delivery_id and is_admin:
            # Admin viewing specific delivery person's dashboard
            delivery_user = app.db.users.find_one({"_id": ObjectId(delivery_id), "role": "delivery"})
            if not delivery_user:
                flash("Delivery personnel not found", "error")
                return redirect(url_for("delivery_view"))
            user = delivery_user
            
        if is_admin and not delivery_id:
            # For admin viewing general delivery dashboard
            pending_requests = list(app.db.delivery_requests.find({
                "status": "pending"
            }).sort("requested_at", DESCENDING))

            # Get all orders that are either out for delivery or delivered
            all_orders = list(app.db.orders.find({
                "status": {"$in": ["Out for Delivery", "Delivered"]}
            }).sort("created_at", DESCENDING))

            # Enhance orders with customer and delivery person details
            for order in all_orders:
                # Add customer details
                if 'user_id' in order:
                    customer = app.db.users.find_one({"_id": order["user_id"]})
                    if customer:
                        order["customer_name"] = customer.get("name")
                        order["customer_phone"] = customer.get("phone")
                        order["customer_email"] = customer.get("email")

                # Add delivery person details
                if 'delivery_id' in order:
                    delivery_person = app.db.users.find_one({"_id": order["delivery_id"]})
                    if delivery_person:
                        order["delivery_name"] = delivery_person.get("name")
                        order["delivery_phone"] = delivery_person.get("phone")

            # Split orders based on status
            assigned_orders = [order for order in all_orders if order["status"] == "Out for Delivery"]
            completed_orders = [order for order in all_orders if order["status"] == "Delivered"]

            # Create admin view profile
            delivery_profile = {
                "name": "Admin Overview",
                "role": "admin",
                "is_available": True,
                "total_pending": len(pending_requests),
                "total_active": len(assigned_orders),
                "total_completed": len(completed_orders)
            }
        else:
            # For delivery person view
            user_id = ObjectId(user["_id"])
            delivery_profile = app.db.users.find_one({"_id": user_id})

            # Get reviews for this delivery person (only count and average)
            reviews = list(app.db.reviews.find({
                "delivery_person_id": str(user_id),
                "type": "delivery"
            }))
            
            # Calculate average rating and review count
            if reviews:
                total_rating = sum(review["rating"] for review in reviews)
                delivery_profile["rating_avg"] = round(total_rating / len(reviews), 1)
                delivery_profile["rating_count"] = len(reviews)
            else:
                delivery_profile["rating_avg"] = 0
                delivery_profile["rating_count"] = 0

            # Get all orders assigned to this delivery person
            pending_requests = list(app.db.delivery_requests.find({
                "delivery_user_id": user_id,
                "status": "pending"
            }).sort("requested_at", DESCENDING))

            assigned_orders = list(app.db.orders.find({
                "delivery_id": user_id,
                "status": "Out for Delivery"
            }).sort("created_at", DESCENDING))

            completed_orders = list(app.db.orders.find({
                "delivery_id": user_id,
                "status": "Delivered"
            }).sort("created_at", DESCENDING).limit(10))
        
        # Handle POST requests (profile updates from the modal form)
        if request.method == "POST":
            # Update delivery profile
            updates = {
                "vehicle_type": request.form.get("vehicle_type", "").strip(),
                "phone": request.form.get("phone", "").strip(),
                "license_number": request.form.get("license_number", "").strip(),
                "current_location": request.form.get("current_location", "").strip(),
                "is_available": request.form.get("is_available") == "true",
                "updated_at": datetime.utcnow()
            }
            
            # Update user basic info if provided
            user_updates = {}
            new_name = request.form.get("name", "").strip()
            if new_name:
                user_updates["name"] = new_name
            
            try:
                # Update delivery profile
                app.db.delivery_profiles.update_one(
                    {"user_id": user_id},
                    {"$set": updates}
                )
                
                # Update user info if needed
                if user_updates:
                    app.db.users.update_one(
                        {"_id": user_id},
                        {"$set": user_updates}
                    )
                    # Update session with new name
                    session["user"]["name"] = new_name
                    session.modified = True
                
                flash("Profile updated successfully!", "success")
                return redirect(url_for("delivery_dashboard"))
                
            except Exception as e:
                flash(f"Error updating profile: {str(e)}", "danger")
                return redirect(url_for("delivery_dashboard"))
        
        # GET request - Show dashboard with data
        delivery_profile = app.db.delivery_profiles.find_one({"user_id": user_id})
        if delivery_profile:
            if "_id" in delivery_profile:
                delivery_profile["_id"] = str(delivery_profile["_id"])
            if "user_id" in delivery_profile and isinstance(delivery_profile["user_id"], ObjectId):
                delivery_profile["user_id"] = str(delivery_profile["user_id"])
        
        # Get pending delivery requests
        pending_requests = list(app.db.delivery_requests.find({
            "delivery_user_id": user_id,
            "status": "pending"
        }))
        
        # Get assigned orders
        assigned_orders = list(app.db.orders.find({
            "assigned_delivery_id": user_id,
            "status": "Out for Delivery"
        }).sort("created_at", DESCENDING))
        
        # Get completed orders
        completed_orders = list(app.db.orders.find({
            "assigned_delivery_id": user_id,
            "status": "Delivered"
        }).sort("created_at", DESCENDING).limit(10))
        
        # Convert ObjectIds and handle items for template
        for order in assigned_orders + completed_orders:
            order["_id"] = str(order["_id"])
            # Ensure items are handled consistently
            items = []
            if isinstance(order.get('items'), list):
                items = order['items']
            elif isinstance(order.get('order_items'), list):
                items = order['order_items']
            order['items'] = items
            order['items_count'] = len(items)
        
        for delivery_request in pending_requests:
            delivery_request["_id"] = str(delivery_request["_id"])
            if "order_id" in delivery_request and isinstance(delivery_request["order_id"], ObjectId):
                delivery_request["order_id"] = str(delivery_request["order_id"])
            # Get order details for each delivery request
            order = app.db.orders.find_one({"_id": ObjectId(delivery_request["order_id"])} if delivery_request.get("order_id") else None)
            if order:
                # Get items list from either items or order_items field
                items = order.get("items", []) if isinstance(order.get("items"), list) else order.get("order_items", [])
                if not isinstance(items, list):
                    items = []
                    
                delivery_request["order_details"] = {
                    "total": order.get("total", 0),
                    "address": order.get("address", ""),
                    "items": items,
                    "items_count": len(items)
                }
        
        # Get user data for the template
        user_data = app.db.users.find_one({"_id": user_id})
        
        # Merge user data into delivery profile for the form
        if delivery_profile and user_data:
            delivery_profile["name"] = user_data.get("name", "")
            
        return render_template("delivery_dashboard.html", 
                            delivery_profile=delivery_profile,
                            pending_requests=pending_requests,
                            assigned_orders=assigned_orders,
                            completed_orders=completed_orders)

    def delivery_update_order_status(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        new_status = request.form.get("status")
        valid_statuses = ["Out for Delivery", "Delivered"]
        
        if new_status not in valid_statuses:
            return jsonify({"ok": False, "msg": "Invalid status"}), 400

        # Verify this order is assigned to the current delivery person
        user_id = ObjectId(session["user"]["_id"])
        order = app.db.orders.find_one({"_id": oid, "assigned_delivery_id": user_id})
        
        if not order:
            return jsonify({"ok": False, "msg": "Order not found or not assigned to you"}), 404

        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )
        return jsonify({"ok": True, "status": new_status})


    # ----------------------
    # Delivery Management
    # ----------------------

    # Pharmacy: Assign delivery to an order
    @app.route("/orders/<order_id>/assign_delivery", methods=["POST"])
    @roles_required("pharmacy")
    def assign_delivery(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        # Verify pharmacy owns this order
        user_id = ObjectId(session["user"]["_id"])
        pharmacy = app.db.pharmacies.find_one({"owner_id": user_id})
        
        if not pharmacy:
            return jsonify({"ok": False, "msg": "Pharmacy not found"}), 404

        order = app.db.orders.find_one({"_id": oid, "pharmacy_ids": pharmacy["_id"]})
        if not order:
            return jsonify({"ok": False, "msg": "Order not found or not authorized"}), 404

        # Get all delivery persons, regardless of availability
        all_delivery_persons = list(app.db.delivery_profiles.find())
        
        return render_template("assign_delivery.html", 
                            order=order, 
                            delivery_persons=all_delivery_persons)

    # Pharmacy: Send delivery request to multiple delivery persons
    @app.route("/orders/<order_id>/request_delivery", methods=["POST"])
    @roles_required("pharmacy")
    def request_delivery(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        # Verify pharmacy owns this order
        user_id = ObjectId(session["user"]["_id"])
        pharmacy = app.db.pharmacies.find_one({"owner_id": user_id})
        
        if not pharmacy:
            return jsonify({"ok": False, "msg": "Pharmacy not found"}), 404

        order = app.db.orders.find_one({"_id": oid, "pharmacy_ids": pharmacy["_id"]})
        if not order:
            return jsonify({"ok": False, "msg": "Order not found or not authorized"}), 404

        # Create delivery requests for all registered delivery persons
        all_delivery_persons = list(app.db.delivery_profiles.find())
        
        delivery_requests = []
        for delivery in all_delivery_persons:
            # Get user details to include name in the request
            delivery_user = app.db.users.find_one({"_id": delivery["user_id"]})
            request_doc = {
                "order_id": oid,
                "delivery_user_id": delivery["user_id"],
                "delivery_user_name": delivery_user.get("name", "Unknown") if delivery_user else "Unknown",
                "pharmacy_id": pharmacy["_id"],
                "status": "pending",  # pending, accepted, rejected
                "requested_at": datetime.utcnow(),
                "responded_at": None,
                "order_details": {
                    "total": order.get("total", 0),
                    "items": order.get("items", []),  # Use items consistently
                    "items_count": len(order.get("items", [])),  # Add count based on items
                    "address": order.get("delivery_address", "Address not available")
                }
            }
            delivery_requests.append(request_doc)
        
        # Insert all requests
        if delivery_requests:
            app.db.delivery_requests.insert_many(delivery_requests)
        
        # Update order status
        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {"status": "Ready for Delivery", "updated_at": datetime.utcnow()}}
        )

        flash(f"Delivery request sent to {len(delivery_requests)} delivery persons!", "success")
        return redirect(url_for("pharmacy_dashboard"))

    # Delivery: Accept delivery request
    @app.route("/delivery/request/<request_id>/accept", methods=["POST"])
    @roles_required("delivery")
    def accept_delivery(request_id):
        try:
            rid = ObjectId(request_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid request id"}), 400

        user_id = ObjectId(session["user"]["_id"])
        
        # Check if request exists and is pending
        delivery_request = app.db.delivery_requests.find_one({
            "_id": rid, 
            "delivery_user_id": user_id,
            "status": "pending"
        })
        
        if not delivery_request:
            return jsonify({"ok": False, "msg": "Request not found or already processed"}), 404

        # Update request status
        app.db.delivery_requests.update_one(
            {"_id": rid},
            {"$set": {"status": "accepted", "responded_at": datetime.utcnow()}}
        )

        # Update order with assigned delivery person
        app.db.orders.update_one(
            {"_id": delivery_request["order_id"]},
            {"$set": {
                "assigned_delivery_id": user_id,
                "status": "Out for Delivery",
                "updated_at": datetime.utcnow()
            }}
        )

        # Mark delivery person as unavailable
        app.db.delivery_profiles.update_one(
            {"user_id": user_id},
            {"$set": {"is_available": False}}
        )

        # Reject all other pending requests for this order
        app.db.delivery_requests.update_many(
            {
                "order_id": delivery_request["order_id"],
                "status": "pending",
                "_id": {"$ne": rid}
            },
            {"$set": {"status": "rejected", "responded_at": datetime.utcnow()}}
        )

        flash("Delivery accepted successfully! Order is now out for delivery.", "success")
        return redirect(url_for("delivery_dashboard"))

    # Delivery: Reject delivery request
    @app.route("/delivery/request/<request_id>/reject", methods=["POST"])
    @roles_required("delivery")
    def reject_delivery(request_id):
        try:
            rid = ObjectId(request_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid request id"}), 400

        user_id = ObjectId(session["user"]["_id"])
        
        # Check if request exists and is pending
        delivery_request = app.db.delivery_requests.find_one({
            "_id": rid, 
            "delivery_user_id": user_id,
            "status": "pending"
        })
        
        if not delivery_request:
            return jsonify({"ok": False, "msg": "Request not found or already processed"}), 404

        # Update request status to rejected
        app.db.delivery_requests.update_one(
            {"_id": rid},
            {"$set": {"status": "rejected", "responded_at": datetime.utcnow()}}
        )

        flash("Delivery request rejected.", "info")
        return redirect(url_for("delivery_dashboard"))

    # Delivery: Mark delivery as completed
    @app.route("/orders/<order_id>/complete", methods=["POST"])
    @roles_required("delivery")
    def complete_delivery(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        user_id = ObjectId(session["user"]["_id"])
        
        # Verify delivery person is assigned to this order
        order = app.db.orders.find_one({"_id": oid, "assigned_delivery_id": user_id})
        if not order:
            return jsonify({"ok": False, "msg": "Order not found or not assigned to you"}), 404

        # Update order status to awaiting confirmation
        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {
                "status": "Awaiting Confirmation",
                "delivered_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }}
        )

        flash("Delivery marked for confirmation. Waiting for customer to confirm receipt.", "info")
        return redirect(url_for("delivery_dashboard"))

    @app.route("/orders/<order_id>/confirm", methods=["POST"])
    @login_required
    def confirm_delivery(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        user_id = ObjectId(session["user"]["_id"])
        
        # Verify this is the customer's order
        order = app.db.orders.find_one({"_id": oid, "user_id": user_id, "status": "Awaiting Confirmation"})
        if not order:
            flash("Order not found or cannot be confirmed.", "danger")
            return redirect(url_for("orders_list"))

        # Update order status to delivered
        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {
                "status": "Delivered",
                "confirmed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }}
        )

        # Mark delivery person as available again
        if order.get("assigned_delivery_id"):
            app.db.delivery_profiles.update_one(
                {"user_id": order["assigned_delivery_id"]},
                {"$set": {"is_available": True}}
            )

        flash("Delivery confirmed successfully!", "success")
        return redirect(url_for("order_detail", order_id=order_id))






    # ----------------------
    # Search/Catalog
    # ----------------------
    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        pharmacy_id = request.args.get("pharmacy", "").strip()
        price_min = request.args.get("min", "").strip()
        price_max = request.args.get("max", "").strip()

        # Build filter
        filt = {"is_active": True}

        # Text search - search in name and category
        if q:
            filt["$or"] = [
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"category": {"$regex": re.escape(q), "$options": "i"}}
            ]

        # Category filter - only apply if not empty and not "all"
        if category and category != "all" and category != "":
            filt["category"] = category

        # Pharmacy filter - only apply if not empty and not "all"
        if pharmacy_id and pharmacy_id != "all" and pharmacy_id != "":
            try:
                filt["pharmacy_id"] = ObjectId(pharmacy_id)
            except Exception:
                # If invalid ObjectId, skip this filter
                pass

        price_query = {}
        if price_min:
            try:
                price_query["$gte"] = float(price_min)
            except ValueError:
                pass
        if price_max:
            try:
                price_query["$lte"] = float(price_max)
            except ValueError:
                pass
        if price_query:
            filt["price"] = price_query

        # Get medicines with filter
        meds = list(app.db.medicines.find(filt).sort("name", ASCENDING))

        # Get categories and pharmacies for filters - only from active medicines
        categories = sorted({m.get("category", "") for m in app.db.medicines.find({"is_active": True}, {"category": 1}) if m.get("category")})
        pharmacies = list(app.db.pharmacies.find({"is_active": True}, {"name": 1, "_id": 1}))
        return render_template("search.html",
                               meds=meds, categories=categories, pharmacies=pharmacies,
                               selected={"q": q, "category": category, "pharmacy": pharmacy_id,
                                         "min": price_min, "max": price_max})

    # ----------------------
    # Cart & Checkout
    # ----------------------
    def _get_cart():
        # Get cart from session or create empty dict
        cart = session.get("cart")
        if cart is None or not isinstance(cart, dict):
            session["cart"] = {}
            cart = {}
        return cart

    @app.route("/cart")
    def cart_view():
        cart = _get_cart()
        items = []
        total = 0.0
        pharmacy_ids = set()  # new variable to track unique pharmacy IDs
        for mid, qty in cart.items():
            med = app.db.medicines.find_one({"_id": ObjectId(mid)})
            if not med:
                continue
            line_total = med["price"] * qty
            total += line_total
            items.append({"med": med, "qty": qty, "line_total": line_total})
            if med.get("pharmacy_id"):
                pharmacy_ids.add(med["pharmacy_id"])
        pharmacies = list(app.db.pharmacies.find({"is_active": True}, {"name": 1, "_id": 1}))
        multiple_pharmacies = (len(pharmacy_ids) > 1)
        return render_template("cart.html", items=items, total=total, pharmacies=pharmacies, multiple_pharmacies=multiple_pharmacies)


    @app.route("/cart/add", methods=["POST"])
    def cart_add():
        med_id = request.form.get("med_id", "")
        qty = int(request.form.get("qty", 1))
        
        try:
            # Validate medicine ID
            medicine_id = ObjectId(med_id)
            medicine = app.db.medicines.find_one({"_id": medicine_id, "is_active": True})
            if not medicine:
                flash("Medicine not found or unavailable.", "danger")
                return redirect(request.referrer or url_for('search'))
                
        except Exception:
            flash("Invalid medicine selection.", "danger")
            return redirect(request.referrer or url_for('search'))

        # Add to cart - FIXED: Ensure cart is properly handled
        cart = _get_cart()
        current_qty = cart.get(med_id, 0)
        cart[med_id] = current_qty + max(1, qty)
        session["cart"] = cart  # Explicitly set session cart
        session.modified = True  # Ensure session is saved
        
        flash(f"{medicine['name']} added to cart!", "success")
        return redirect(request.referrer or url_for('search'))



    @app.route("/cart/update", methods=["POST"])
    def cart_update():
        med_id = request.form.get("med_id", "")
        qty = max(0, int(request.form.get("qty", 0)))
        
        try:
            # Validate medicine ID
            medicine_id = ObjectId(med_id)
            medicine = app.db.medicines.find_one({"_id": medicine_id})
        except Exception:
            flash("Invalid medicine selection.", "danger")
            return redirect(url_for('cart_view'))

        cart = _get_cart()
        if qty == 0:
            cart.pop(med_id, None)
            flash(f"{medicine['name']} removed from cart.", "info")
        else:
            cart[med_id] = qty
            flash(f"{medicine['name']} quantity updated.", "success")
        
        session.modified = True
        return redirect(url_for('cart_view'))

    @app.route("/checkout", methods=["GET", "POST"])
    @login_required
    def checkout():
        if request.method == "POST":
            # If coming from the cart page with selected items
            selected_items = request.form.getlist("selected_items")
            if selected_items:
                # Store selected items in session
                cart = _get_cart()
                selected_cart = {mid: qty for mid, qty in cart.items() if mid in selected_items}
                session['checkout_items'] = selected_cart
                session.modified = True
                
                # Prepare items for display
                items = []
                total = 0.0
                for mid, qty in selected_cart.items():
                    med = app.db.medicines.find_one({"_id": ObjectId(mid)})
                    if med:
                        line_total = med["price"] * qty
                        total += line_total
                        items.append({
                            "med": med,
                            "qty": qty,
                            "line_total": line_total
                        })
                
                pharmacies = list(app.db.pharmacies.find({"is_active": True}))
                return render_template("checkout.html", cart_items=items, cart_total=total, pharmacies=pharmacies)

            # If coming from the checkout page with address (placing order)
            user = session["user"]
            address = request.form.get("address", "").strip()

            if not address:
                flash("Delivery address required.", "warning")
                return redirect(url_for("checkout"))

            # Use the selected items stored in session
            cart = session.get('checkout_items', {})
            print("DEBUG: Cart contents before order creation:", cart)
            if not cart:
                flash("Cart is empty.", "warning")
                return redirect(url_for("cart_view"))

            # Build order items
            items = []
            total = 0.0
            pharmacy_ids = set()

            for mid, qty in cart.items():
                try:
                    med = app.db.medicines.find_one({"_id": ObjectId(mid), "is_active": True})
                    if not med:
                        continue

                    item_total = med["price"] * qty
                    items.append({
                        "medicine_id": med["_id"],
                        "name": med["name"],
                        "category": med.get("category", "General"),
                        "unit_price": float(med["price"]),
                        "qty": int(qty),
                        "line_total": float(item_total)
                    })
                    total += item_total

                    if med.get("pharmacy_id"):
                        pharmacy_ids.add(med["pharmacy_id"])

                except Exception as e:
                    continue
            print(items)
            # NEW: Check if medicines from different pharmacies are present
            if len(pharmacy_ids) > 1:
                flash("Medicines from different pharmacies cannot be ordered together. Please place separate orders.", "warning")
                return redirect(url_for('cart_view'))

            print("DEBUG: Items to be saved in order:", items)
            if not items:
                flash("No valid items in cart.", "danger")
                return redirect(url_for("cart_view"))

            # Get customer information
            user_data = app.db.users.find_one({"_id": ObjectId(user["_id"])})
            
            # Create order
            order_doc = {
                "user_id": ObjectId(user["_id"]),
                "customer_name": user_data.get("name", ""),  # Get name from user profile
                "phone_number": request.form.get("phone", ""),  # Get phone from checkout form
                "notes": request.form.get("instructions", ""),  # Get delivery instructions
                "items": items,  # Use items as the standard field
                "order_items": items,  # Keep for backward compatibility
                "total": round(total, 2),
                "address": address,
                "status": "Processing",
                "pharmacy_ids": list(pharmacy_ids),
                "assigned_delivery_id": None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }

            # Save to database
            result = app.db.orders.insert_one(order_doc)
            order_id = result.inserted_id

            # Deduct stock
            for item in items:
                app.db.medicines.update_one(
                    {"_id": item["medicine_id"]},
                    {"$inc": {"stock": -item["qty"]}}
                )

            # Clear checkout items and remove those items from cart
            checkout_items = session.pop("checkout_items", {})
            cart = _get_cart()
            for item_id in checkout_items:
                cart.pop(item_id, None)
            session["cart"] = cart
            session.modified = True

            print("DEBUG: Order inserted with order_doc:", order_doc, "and order_id:", order_id)

            flash("Order placed successfully!", "success")
            return redirect(url_for("order_detail", order_id=str(order_id)))

        # GET request
        selected_cart = session.get('checkout_items')
        if not selected_cart:
            flash("Please select items from your cart first.", "warning")
            return redirect(url_for("cart_view"))
        
        # Prepare items for display
        items = []
        total = 0.0
        for mid, qty in selected_cart.items():
            med = app.db.medicines.find_one({"_id": ObjectId(mid)})
            if med:
                line_total = med["price"] * qty
                total += line_total
                items.append({
                    "med": med,
                    "qty": qty,
                    "line_total": line_total
                })
        
        for mid, qty in cart.items():
            try:
                med = app.db.medicines.find_one({"_id": ObjectId(mid)})
                if med:
                    line_total = med["price"] * qty
                    total += line_total
                    items.append({
                        "med": med, 
                        "qty": qty, 
                        "line_total": line_total
                    })
            except:
                continue
        
        pharmacies = list(app.db.pharmacies.find({"is_active": True}))
        
        return render_template("checkout.html", 
                            cart_items=items, 
                            cart_total=total, 
                            pharmacies=pharmacies)
    @app.route("/test/cart")
    def test_cart():
        # Test if cart is working
        cart = _get_cart()
        # Convert ObjectId keys to strings if present
        cart_serialized = {}
        for k, v in cart.items():
            if isinstance(k, ObjectId):
                cart_serialized[str(k)] = v
            else:
                cart_serialized[k] = v
        return jsonify({
            "cart": cart_serialized,
            "cart_type": type(cart).__name__,
            "cart_count": len(cart_serialized)
        })



    # Orders (User)
    # ----------------------
    @app.route("/orders")
    @login_required
    def orders_list():
        user_id = ObjectId(session["user"]["_id"])
        role = session["user"]["role"]
        q = {}

        if role == "user":
            q["user_id"] = user_id
        elif role == "pharmacy":
            # Show orders containing items from this pharmacy
            pharmacy = app.db.pharmacies.find_one({"owner_id": user_id})
            if pharmacy:
                q["pharmacy_ids"] = pharmacy["_id"]
            else:
                q["pharmacy_ids"] = None  # none will match
        elif role == "delivery":
            q["assigned_delivery_id"] = user_id
        elif role == "admin":
            pass  # all orders

        orders = list(app.db.orders.find(q).sort("created_at", DESCENDING))
        
        # Convert any ObjectIds to strings and ensure order_items is properly handled
        for order in orders:
            order['_id'] = str(order['_id'])
            order['user_id'] = str(order['user_id'])
            if 'assigned_delivery_id' in order and order['assigned_delivery_id']:
                order['assigned_delivery_id'] = str(order['assigned_delivery_id'])
            
            # Handle both old (items) and new (order_items) field names
            if 'order_items' in order and isinstance(order['order_items'], list):
                order['order_items'] = order['order_items']
            elif 'items' in order and isinstance(order['items'], list):
                order['order_items'] = order['items']
            else:
                order['order_items'] = []
        
        return render_template("order_history.html", orders=orders)

    @app.route("/orders/<order_id>")
    @login_required
    def order_detail(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            abort(404)
        
        order = app.db.orders.find_one({"_id": oid})
        if not order:
            abort(404)

        # Access control - FIXED for pharmacy users
        user = session["user"]
        uid = ObjectId(user["_id"])
        role = user["role"]
        
        # Add customer details
        if 'user_id' in order:
            customer = app.db.users.find_one({"_id": order["user_id"]})
            if customer:
                order["customer_name"] = customer.get("name")
                order["customer_phone"] = customer.get("phone")
                order["customer_email"] = customer.get("email")

        # Add delivery person details if assigned
        if 'delivery_id' in order:
            delivery = app.db.users.find_one({"_id": order["delivery_id"]})
            if delivery:
                order["delivery_name"] = delivery.get("name")
                order["delivery_phone"] = delivery.get("phone")
        
        # Add user details to order
        if 'user_id' in order:
            customer = app.db.users.find_one({"_id": order["user_id"]})
            if customer:
                order["customer_name"] = customer.get("name")
                order["customer_phone"] = customer.get("phone")
                order["customer_email"] = customer.get("email")

        # Add delivery person details if assigned
        if 'delivery_id' in order:
            delivery_person = app.db.users.find_one({"_id": order["delivery_id"]})
            if delivery_person:
                order["delivery_name"] = delivery_person.get("name")
                order["delivery_phone"] = delivery_person.get("phone")
                order["delivery_id_str"] = str(delivery_person["_id"])
                
                # Get delivery person's current rating
                reviews = list(app.db.reviews.find({
                    "delivery_person_id": order["delivery_id_str"],
                    "type": "delivery"
                }))
                if reviews:
                    total_rating = sum(review["rating"] for review in reviews)
                    order["delivery_rating_avg"] = round(total_rating / len(reviews), 1)
                    order["delivery_rating_count"] = len(reviews)
                else:
                    order["delivery_rating_avg"] = 0
                    order["delivery_rating_count"] = 0

        # Ensure consistent items field
        if 'items' in order and isinstance(order['items'], list):
            order['items'] = order['items']
        elif 'order_items' in order and isinstance(order['order_items'], list):
            order['items'] = order['order_items']
        else:
            order['items'] = []
        
        if role == "user":
            # Users can only see their own orders
            if order["user_id"] != uid:
                abort(403)
                
        elif role == "pharmacy":
            # Pharmacies can see orders that contain their medicines
            pharmacy = app.db.pharmacies.find_one({"owner_id": uid})
            if not pharmacy:
                abort(403)
            # Check if this order contains medicines from this pharmacy
            if pharmacy["_id"] not in order.get("pharmacy_ids", []):
                abort(403)
                
        elif role == "delivery":
            # Delivery can only see orders assigned to them
            if order.get("assigned_delivery_id") != uid:
                abort(403)
                
        # admin can see all orders (no check needed)

        # Convert ObjectIds to strings for template safety
        order["_id"] = str(order["_id"])
        order["user_id"] = str(order["user_id"])
        
        if order.get("assigned_delivery_id") and isinstance(order["assigned_delivery_id"], ObjectId):
            order["assigned_delivery_id"] = str(order["assigned_delivery_id"])
        
        # Handle pharmacy_id for the order
        if order.get("pharmacy_id"):
            order["pharmacy_id"] = str(order["pharmacy_id"])
        elif order.get("pharmacy_ids") and order["pharmacy_ids"]:
            # Use the first pharmacy_id if we have multiple
            order["pharmacy_id"] = str(order["pharmacy_ids"][0]) if isinstance(order["pharmacy_ids"][0], ObjectId) else order["pharmacy_ids"][0]
        
        if order.get("pharmacy_ids"):
            order["pharmacy_ids"] = [str(pid) if isinstance(pid, ObjectId) else pid for pid in order["pharmacy_ids"]]
        
        # Get and process order items
        order_items = order.get('order_items', [])
        if isinstance(order_items, list):
            for item in order_items:
                if 'medicine_id' in item and isinstance(item['medicine_id'], ObjectId):
                    item['medicine_id'] = str(item['medicine_id'])
                if 'pharmacy_id' in item and isinstance(item['pharmacy_id'], ObjectId):
                    item['pharmacy_id'] = str(item['pharmacy_id'])
        else:
            order_items = []
        order['order_items'] = order_items
        
        return render_template("order_tracking.html", order=order)    
    # ----------------------
    # Order Status Updates
    # ----------------------
    @app.route("/orders/<order_id>/status", methods=["POST"])
    @login_required
    def order_update_status(order_id):
        new_status = request.form.get("status")
        valid_flow = ["Pending", "Processing", "Ready for Delivery", "Out for Delivery", "Delivered","Cancelled"]
        if new_status not in valid_flow:
            return jsonify({"ok": False, "msg": "Invalid status"}), 400

        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order id"}), 400

        order = app.db.orders.find_one({"_id": oid})
        if not order:
            return jsonify({"ok": False, "msg": "Order not found"}), 404

        user = session["user"]
        uid = ObjectId(user["_id"])
        role = user["role"]

        # Permissions: pharmacy can set Pending/Processing; delivery can set Out for Delivery/Delivered; admin can set any
        allowed = False
        if role == "admin":
            allowed = True
        elif role == "pharmacy":
            pharm = app.db.pharmacies.find_one({"owner_id": uid})
            if pharm and pharm["_id"] in order.get("pharmacy_ids", []):
                allowed = new_status in {"Pending", "Processing", "Out for Delivery"}
        elif role == "delivery":
            allowed = new_status in {"Out for Delivery", "Delivered"} and order.get("assigned_delivery_id") == uid

        if not allowed:
            return jsonify({"ok": False, "msg": "Not allowed"}), 403

        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )
        return jsonify({"ok": True, "status": new_status})
    


    # ----------------------
    # Order Cancellation
    # ----------------------
    @app.route("/orders/<order_id>/cancel", methods=["POST"])
    @login_required
    def cancel_order(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            flash("Invalid order ID.", "danger")
            return redirect(url_for('orders_list'))

        order = app.db.orders.find_one({"_id": oid})
        if not order:
            flash("Order not found.", "danger")
            return redirect(url_for('orders_list'))

        # Check if user owns this order
        user_id = ObjectId(session["user"]["_id"])
        if order["user_id"] != user_id:
            flash("You can only cancel your own orders.", "danger")
            return redirect(url_for('orders_list'))

        # Check if order can be cancelled (only Pending or Processing)
        if order["status"] not in ["Pending", "Processing"]:
            flash("This order cannot be cancelled at this stage.", "danger")
            return redirect(url_for('order_detail', order_id=order_id))

        # Restore stock
        for item in order["items"]:
            app.db.medicines.update_one(
                {"_id": item["medicine_id"]},
                {"$inc": {"stock": item["qty"]}}
            )

        # Update order status
        app.db.orders.update_one(
            {"_id": oid},
            {"$set": {"status": "Cancelled", "updated_at": datetime.utcnow()}}
        )

        flash("Order cancelled successfully. Stock has been restored.", "success")
        return redirect(url_for('order_detail', order_id=order_id))
    # ----------------------
    # Pharmacy Panel - Stock Management
    # ----------------------
    @app.route("/pharmacy/dashboard")
    @app.route("/pharmacy/dashboard/<pharmacy_id>")
    @roles_required("pharmacy", "admin")
    def pharmacy_dashboard(pharmacy_id=None):
        user = session.get("user")
        
        if pharmacy_id and user["role"] == "admin":
            # Admin viewing specific pharmacy
            pharmacy = app.db.pharmacies.find_one({"_id": ObjectId(pharmacy_id)})
            if not pharmacy:
                flash("Pharmacy not found.", "warning")
                return redirect(url_for("admin_view_pharmacies"))
            owner_id = pharmacy["owner_id"]
            
            # Get owner's information for the view
            owner = app.db.users.find_one({"_id": owner_id})
            if owner:
                pharmacy["owner_name"] = owner["name"]
            
        elif user["role"] == "admin":
            # Admin without specific pharmacy - redirect to pharmacy list
            return redirect(url_for("admin_view_pharmacies"))
        else:
            # Regular pharmacy owner
            owner_id = ObjectId(user["_id"])
            pharmacy = app.db.pharmacies.find_one({"owner_id": owner_id})
            if not pharmacy:
                flash("Pharmacy profile not found.", "danger")
                return redirect(url_for("index"))
        
        # Get medicines for this pharmacy
        meds = list(app.db.medicines.find({"pharmacy_id": pharmacy["_id"]}).sort("name", ASCENDING))
        
        # Convert ObjectIds to strings
        for med in meds:
            med["_id"] = str(med["_id"])
            med["pharmacy_id"] = str(med["pharmacy_id"])
        
        # Get orders that contain medicines from this pharmacy
        orders = list(app.db.orders.find({"pharmacy_ids": pharmacy["_id"]}).sort("created_at", DESCENDING).limit(20))
        
        # Convert order ObjectIds to strings and add user info
        for order in orders:
            order["_id"] = str(order["_id"])
            order["user_id"] = str(order["user_id"])
            if "pharmacy_ids" in order:
                order["pharmacy_ids"] = [str(pid) for pid in order["pharmacy_ids"]]
            
            # Get user info for each order
            user = app.db.users.find_one({"_id": ObjectId(order["user_id"])})
            if user:
                order["user_name"] = user["name"]
        
        return render_template("pharmacy_panel.html", 
                            pharmacy=pharmacy, 
                            meds=meds, 
                            orders=orders,
                            is_admin_view=user["role"] == "admin")
        
        # Convert OrderIds and related ObjectIds to strings for template
        for order in orders:
            order["_id"] = str(order["_id"])
            order["user_id"] = str(order["user_id"])
            order["pharmacy_ids"] = [str(pid) for pid in order.get("pharmacy_ids", [])]
        
        return render_template("pharmacy_panel.html", pharmacy=pharmacy, meds=meds, orders=orders)

    @app.route("/pharmacy/medicine/add", methods=["POST"])
    @roles_required("pharmacy")
    def pharmacy_add_medicine():
        owner_id = ObjectId(session["user"]["_id"])
        pharmacy = app.db.pharmacies.find_one({"owner_id": owner_id})
        if not pharmacy:
            return jsonify({"ok": False, "msg": "Pharmacy not found"}), 404

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price = float(request.form.get("price", "0") or 0)
        stock = int(request.form.get("stock", "0") or 0)
        is_active = request.form.get("is_active", "true").lower() == "true"

        if not name:
            return jsonify({"ok": False, "msg": "Name required"}), 400

        # Handle image upload
        image_path = None
        if "image" in request.files:
            image_path = save_medicine_image(request.files["image"])

        doc = {
            "name": name,
            "category": category,
            "price": price,
            "stock": stock,
            "pharmacy_id": pharmacy["_id"],
            "is_active": is_active,
            "image_path": image_path,
            "created_at": datetime.utcnow()
        }
        app.db.medicines.insert_one(doc)
        return redirect(url_for("pharmacy_dashboard"))

    @app.route("/pharmacy/medicine/<mid>/update", methods=["POST"])
    @roles_required("pharmacy")
    def pharmacy_update_medicine(mid):
        owner_id = ObjectId(session["user"]["_id"])
        pharmacy = app.db.pharmacies.find_one({"owner_id": owner_id})
        if not pharmacy:
            return jsonify({"ok": False, "msg": "Pharmacy not found"}), 404

        try:
            oid = ObjectId(mid)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid id"}), 400

        med = app.db.medicines.find_one({"_id": oid})
        if not med or med["pharmacy_id"] != pharmacy["_id"]:
            return jsonify({"ok": False, "msg": "Not allowed"}), 403

        updates = {}
        if "name" in request.form: updates["name"] = request.form["name"].strip()
        if "category" in request.form: updates["category"] = request.form["category"].strip()
        if "price" in request.form: updates["price"] = float(request.form["price"] or med["price"])
        if "stock" in request.form: updates["stock"] = int(request.form["stock"] or med["stock"])
        if "is_active" in request.form: updates["is_active"] = request.form["is_active"].lower() == "true"

        if not updates:
            flash("No changes provided", "warning")
            return redirect(url_for("pharmacy_dashboard"))

        app.db.medicines.update_one({"_id": oid}, {"$set": updates})
        status_msg = "Medicine activated" if updates.get("is_active") else "Medicine deactivated"
        flash(status_msg, "success")
        return redirect(url_for("pharmacy_dashboard"))

    # ----------------------
    # Stock Management Endpoint (FIX for BuildError)
    # ----------------------
    @app.route("/pharmacy/medicine/<mid>/update_stock", methods=["POST"])
    @roles_required("pharmacy")
    def update_stock(mid):
        """Update stock for a specific medicine"""
        owner_id = ObjectId(session["user"]["_id"])
        pharmacy = app.db.pharmacies.find_one({"owner_id": owner_id})
        if not pharmacy:
            return jsonify({"ok": False, "msg": "Pharmacy not found"}), 404

        try:
            oid = ObjectId(mid)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid medicine id"}), 400

        # Verify the medicine belongs to this pharmacy
        med = app.db.medicines.find_one({"_id": oid, "pharmacy_id": pharmacy["_id"]})
        if not med:
            return jsonify({"ok": False, "msg": "Medicine not found or not authorized"}), 404

        # Get new stock value from request
        new_stock = request.form.get("stock")
        if new_stock is None:
            return jsonify({"ok": False, "msg": "Stock value required"}), 400

        try:
            stock_value = int(new_stock)
            if stock_value < 0:
                return jsonify({"ok": False, "msg": "Stock cannot be negative"}), 400
        except ValueError:
            return jsonify({"ok": False, "msg": "Invalid stock value"}), 400

        # Update the stock
        app.db.medicines.update_one(
            {"_id": oid},
            {"$set": {"stock": stock_value, "updated_at": datetime.utcnow()}}
        )

        flash("Stock updated successfully!", "success")
        return redirect(url_for('pharmacy_dashboard'))

    # ----------------------
    # Reviews & Ratings
    # ----------------------
    @app.route("/reviews/<pharmacy_id>", methods=["GET", "POST"])
    @login_required
    def reviews(pharmacy_id):
        try:
            # Convert string ID to ObjectId
            pid = ObjectId(pharmacy_id)
            
            # Verify pharmacy exists
            pharmacy = app.db.pharmacies.find_one({"_id": pid})
            if not pharmacy:
                flash("Pharmacy not found.", "error")
                return redirect(url_for("home"))
                
        except Exception as e:
            print(f"Error in reviews route: {str(e)}")  # Debug log
            flash("Invalid pharmacy ID.", "error")
            return redirect(url_for("home"))

        if request.method == "POST":
            review_type = request.form.get("type", "pharmacy")
            rating = int(request.form.get("rating", "0"))
            comment = request.form.get("comment", "").strip()
            user_id = ObjectId(session["user"]["_id"])
            
            if rating < 1 or rating > 5:
                flash("Rating must be 1–5.", "warning")
                return redirect(url_for("reviews", pharmacy_id=pharmacy_id))

            # Create review document
            review_doc = {
                "user_id": user_id,
                "rating": rating,
                "comment": comment,
                "type": review_type,
                "created_at": datetime.utcnow()
            }

            # Add appropriate ID based on review type
            if review_type == "pharmacy":
                review_doc["pharmacy_id"] = pid
            elif review_type == "delivery":
                delivery_id = request.form.get("delivery_person_id")
                if not delivery_id:
                    flash("Delivery person ID is required for delivery review.", "error")
                    return redirect(url_for("reviews", pharmacy_id=pharmacy_id))
                review_doc["delivery_person_id"] = delivery_id

            # Insert the review
            app.db.reviews.insert_one(review_doc)

            # Update ratings based on review type
            if review_type == "pharmacy":
                # Update pharmacy ratings
                agg = list(app.db.reviews.aggregate([
                    {"$match": {"pharmacy_id": pid, "type": "pharmacy"}},
                    {"$group": {"_id": "$pharmacy_id", "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}}
                ]))
                if agg:
                    app.db.pharmacies.update_one(
                        {"_id": pid},
                        {"$set": {"rating_avg": round(float(agg[0]["avg"]), 2), "rating_count": agg[0]["count"]}}
                    )
            elif review_type == "delivery" and delivery_id:
                # Update delivery person ratings
                try:
                    delivery_person_id = ObjectId(delivery_id)
                    agg = list(app.db.reviews.aggregate([
                        {"$match": {"delivery_person_id": delivery_id, "type": "delivery"}},
                        {"$group": {"_id": "$delivery_person_id", "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}}
                    ]))
                    if agg:
                        app.db.users.update_one(
                            {"_id": delivery_person_id},
                            {"$set": {"rating_avg": round(float(agg[0]["avg"]), 2), "rating_count": agg[0]["count"]}}
                        )
                except Exception as e:
                    print(f"Error updating delivery ratings: {str(e)}")

            flash("Review submitted successfully.", "success")
            return redirect(url_for("reviews", pharmacy_id=pharmacy_id))

        pharmacy = app.db.pharmacies.find_one({"_id": pid})
        if not pharmacy:
            abort(404)
            
        # Get both pharmacy and delivery reviews
        pharmacy_reviews = list(app.db.reviews.find({"pharmacy_id": pid, "type": "pharmacy"}).sort("created_at", DESCENDING))
        
        # Get order id from referrer if available
        order_id = request.args.get('order_id')
        order = None
        delivery_reviews = []
        delivery_person = None

        if order_id:
            try:
                order = app.db.orders.find_one({"_id": ObjectId(order_id)})
                if order:
                    order["_id"] = str(order["_id"])
                    # If order has a delivery person, get their details and reviews
                    if "delivery_id" in order:
                        delivery_person = app.db.users.find_one({"_id": order["delivery_id"]})
                        if delivery_person:
                            delivery_person["_id"] = str(delivery_person["_id"])
                            delivery_reviews = list(app.db.reviews.find({
                                "delivery_person_id": str(delivery_person["_id"]),
                                "type": "delivery"
                            }).sort("created_at", DESCENDING))
            except Exception as e:
                print(f"Error getting order or delivery details: {str(e)}")

        return render_template(
            "reviews.html", 
            pharmacy=pharmacy, 
            pharmacy_reviews=pharmacy_reviews,
            delivery_reviews=delivery_reviews,
            delivery_person=delivery_person,
            order=order
        )

    # Re-order
    # ----------------------
    @app.route("/orders/<order_id>/reorder", methods=["POST"])
    @login_required
    def reorder(order_id):
        user_id = ObjectId(session["user"]["_id"])
        try:
            oid = ObjectId(order_id)
        except Exception:
            flash("Invalid order ID", "error")
            return redirect(url_for('order_history'))

        order = app.db.orders.find_one({"_id": oid, "user_id": user_id})
        if not order:
            flash("Order not found", "error")
            return redirect(url_for('order_history'))

        # Get the items array from the order
        items = order.get("items") or order.get("order_items", [])
        if not items:
            flash("No items found in the order", "error")
            return redirect(url_for('order_history'))

        # Put items back into cart with same quantities
        cart = _get_cart()
        added_count = 0
        
        for item in items:
            # Handle both possible item structures
            medicine_id = str(item.get("medicine_id", item.get("_id")))
            qty = int(item.get("qty", item.get("quantity", 1)))
            
            if medicine_id:
                # Verify medicine still exists and is in stock
                medicine = app.db.medicines.find_one({"_id": ObjectId(medicine_id)})
                if medicine and medicine.get("stock", 0) > 0:
                    cart[medicine_id] = cart.get(medicine_id, 0) + qty
                    added_count += qty

        if added_count > 0:
            session["cart"] = cart
            session.modified = True
            flash(f"Added {added_count} items to cart", "success")
        else:
            flash("Could not add any items to cart. Items may be out of stock.", "warning")
        
        return redirect(url_for('cart_view'))

    # Schedules / Reminders
    @app.route("/schedules", methods=["GET", "POST", "DELETE"])
    @login_required
    def schedules():
        user_id = ObjectId(session["user"]["_id"])

        if request.method == "POST":
            freq = request.form.get("frequency", "weekly")  # "weekly" or "monthly"
            medicine_names = [s.strip() for s in request.form.get("medicines", "").split(",") if s.strip()]
            notes = request.form.get("notes", "").strip()
            start_date_str = request.form.get("start_date", "")
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            except Exception:
                start_date = datetime.utcnow()

            doc = {
                "user_id": user_id,
                "frequency": freq,
                "medicines": medicine_names,
                "notes": notes,
                "start_date": start_date,
                "created_at": datetime.utcnow()
            }
            app.db.schedules.insert_one(doc)
            return jsonify({"ok": True})

        if request.method == "DELETE":
            sid = request.args.get("id", "")
            try:
                s_oid = ObjectId(sid)
            except Exception:
                return jsonify({"ok": False, "msg": "Invalid id"}), 400
            app.db.schedules.delete_one({"_id": s_oid, "user_id": user_id})
            return jsonify({"ok": True})

        # GET
        search = request.args.get("search", "").strip()
        q = {"user_id": user_id}
        if search:
            q["medicines"] = {"$elemMatch": {"$regex": re.escape(search), "$options": "i"}}
        scheds = list(app.db.schedules.find(q).sort("created_at", DESCENDING))
        return render_template("schedule.html", schedules=scheds)
    @app.route("/debug/order/<order_id>")
    @login_required
    def debug_order(order_id):
        try:
            oid = ObjectId(order_id)
            order = app.db.orders.find_one({"_id": oid})
            
            if not order:
                return jsonify({"error": "Order not found"}), 404
            
            # Convert ObjectId to string for JSON serialization
            order['_id'] = str(order['_id'])
            order['user_id'] = str(order['user_id'])
            
            # Check the items field
            items = order.get('items', [])
            order['items_type'] = str(type(items))
            order['items_length'] = len(items) if hasattr(items, '__len__') else 'N/A'
            order['items_content'] = items
            
            return jsonify(order)
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/debug/orders")
    @login_required
    def debug_orders():
        user_id = ObjectId(session["user"]["_id"])
        orders = list(app.db.orders.find({"user_id": user_id}))
        
        result = []
        for order in orders:
            order_data = {
                '_id': str(order['_id']),
                'status': order.get('status'),
                'total': order.get('total'),
                'items_count': len(order.get('items', [])),
                'items_type': str(type(order.get('items'))),
                'created_at': order.get('created_at')
            }
            result.append(order_data)
        
        return jsonify(result)
    
    # Admin Panel
    @app.route("/admin")
    @roles_required("admin")
    def admin_dashboard():
        users = list(app.db.users.find().sort("created_at", DESCENDING).limit(20))
        pharmacies = list(app.db.pharmacies.find().sort("created_at", DESCENDING).limit(20))
        medicines = list(app.db.medicines.find().sort("created_at", DESCENDING).limit(20))
        orders = list(app.db.orders.find().sort("created_at", DESCENDING).limit(20))
        return render_template("admin_panel.html", users=users, pharmacies=pharmacies, medicines=medicines, orders=orders)

    @app.route("/admin/customers")
    @roles_required("admin")
    def admin_view_customers():
        # Get all customers (users with role="user")
        pipeline = [
            {"$match": {"role": "user"}},
            {
                "$lookup": {
                    "from": "orders",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "orders"
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                    "email": 1,
                    "is_active": 1,
                    "created_at": 1,
                    "order_count": {"$size": "$orders"}
                }
            },
            {"$sort": {"created_at": -1}}
        ]
        
        customers = list(app.db.users.aggregate(pipeline))
        
        # Convert ObjectIds to strings
        for customer in customers:
            customer["_id"] = str(customer["_id"])
            
        return render_template("customer_view.html", customers=customers)

    @app.route("/admin/pharmacies")
    @roles_required("admin")
    def admin_view_pharmacies():
        # Get all pharmacies with their medicine and order counts
        pipeline = [
            {
                "$lookup": {
                    "from": "users",
                    "localField": "owner_id",
                    "foreignField": "_id",
                    "as": "owner"
                }
            },
            {
                "$lookup": {
                    "from": "medicines",
                    "localField": "_id",
                    "foreignField": "pharmacy_id",
                    "as": "medicines"
                }
            },
            {
                "$lookup": {
                    "from": "orders",
                    "localField": "_id",
                    "foreignField": "pharmacy_ids",
                    "as": "orders"
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                    "owner_name": {"$arrayElemAt": ["$owner.name", 0]},
                    "is_active": 1,
                    "created_at": 1,
                    "medicine_count": {"$size": "$medicines"},
                    "order_count": {"$size": "$orders"}
                }
            },
            {"$sort": {"created_at": -1}}
        ]
        
        pharmacies = list(app.db.pharmacies.aggregate(pipeline))
        
        # Convert ObjectIds to strings
        for pharmacy in pharmacies:
            pharmacy["_id"] = str(pharmacy["_id"])
            
        return render_template("pharmacy_view.html", pharmacies=pharmacies)

    @app.route("/admin/pharmacies/<pharmacy_id>/dashboard")
    @roles_required("admin")
    def admin_view_pharmacy_dashboard(pharmacy_id):
        # Get the pharmacy's information
        pharmacy = app.db.pharmacies.find_one({"_id": ObjectId(pharmacy_id)})
        if not pharmacy:
            flash("Pharmacy not found.", "error")
            return redirect(url_for("admin_view_pharmacies"))
        
        # Get the pharmacy owner's information
        owner = app.db.users.find_one({"_id": pharmacy["owner_id"]})
        if not owner:
            flash("Pharmacy owner not found.", "error")
            return redirect(url_for("admin_view_pharmacies"))
        
        # Store the original admin user
        admin_user = session["user"]
        
        # Temporarily set the session user to the pharmacy owner
        session["user"] = {
            "_id": str(owner["_id"]),
            "name": owner["name"],
            "email": owner["email"],
            "role": "pharmacy",
            "is_active": owner["is_active"],
            "viewed_by_admin": True  # Add this flag to indicate admin view
        }
        
        try:
            # Redirect to pharmacy dashboard
            return redirect(url_for("pharmacy_dashboard"))
        finally:
            # Restore the admin user to the session
            session["user"] = admin_user

    @app.route("/admin/customers/<user_id>/dashboard")
    @roles_required("admin")
    def admin_view_customer_dashboard(user_id):
        # Get the customer information
        customer = app.db.users.find_one({"_id": ObjectId(user_id), "role": "user"})
        if not customer:
            flash("Customer not found.", "error")
            return redirect(url_for("admin_view_customers"))
        
        # Get customer's orders
        orders = list(app.db.orders.find({"user_id": ObjectId(user_id)}).sort("created_at", DESCENDING))
        
        # Convert ObjectIds to strings
        customer["_id"] = str(customer["_id"])
        for order in orders:
            order["_id"] = str(order["_id"])
            order["user_id"] = str(order["user_id"])
            if "pharmacy_ids" in order:
                order["pharmacy_ids"] = [str(pid) for pid in order["pharmacy_ids"]]
        
        return render_template("user_dashboard.html", 
                            user=customer, 
                            orders=orders, 
                            is_admin_view=True)

    @app.route("/admin/toggle_user/<uid>", methods=["POST"])
    @roles_required("admin")
    def admin_toggle_user(uid):
        try:
            oid = ObjectId(uid)
        except Exception:
            return jsonify({"ok": False}), 400
        user = app.db.users.find_one({"_id": oid})
        if not user:
            return jsonify({"ok": False}), 404
        app.db.users.update_one({"_id": oid}, {"$set": {"is_active": not user.get("is_active", True)}})
        return jsonify({"ok": True})

    # ----------------------
    # Admin Management Functions
    # ----------------------
    @app.route("/admin/update_order/<order_id>", methods=["POST"])
    @roles_required("admin")
    def update_order(order_id):
        try:
            oid = ObjectId(order_id)
        except Exception:
            return jsonify({"ok": False, "msg": "Invalid order ID"}), 400
            
        status = request.form.get("status")
        if not status:
            return jsonify({"ok": False, "msg": "Status is required"}), 400
            
        result = app.db.orders.update_one(
            {"_id": oid},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}}
        )
        
        if result.matched_count == 0:
            return jsonify({"ok": False, "msg": "Order not found"}), 404
            
        flash("Order status updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/create_user", methods=["POST"])
    @roles_required("admin")
    def admin_create_user():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        
        if not name or not email or not password:
            return jsonify({"ok": False, "msg": "All fields are required"}), 400
            
        if app.db.users.find_one({"email": email}):
            return jsonify({"ok": False, "msg": "Email already registered"}), 400
            
        hashed = generate_password_hash(password)
        user_doc = {
            "name": name,
            "email": email,
            "password": hashed,
            "role": role,
            "created_at": datetime.utcnow(),
            "is_active": True,
        }
        app.db.users.insert_one(user_doc)
        
        return jsonify({"ok": True, "msg": "User created successfully"})


    # Lightweight APIs (JSON)
    @app.route("/api/medicines")
    def api_medicines():
        # For AJAX filters
        q = request.args.get("q", "").strip()
        filt = {"is_active": True}
        if q:
            filt["name"] = {"$regex": re.escape(q), "$options": "i"}
        meds = list(app.db.medicines.find(filt).sort("name", ASCENDING).limit(50))
        for m in meds:
            m["_id"] = str(m["_id"])
            if m.get("pharmacy_id"):
                m["pharmacy_id"] = str(m["pharmacy_id"])
        return jsonify(meds)


    # Update complaint status route is defined above

    @app.route("/health")
    def health():
        try:
            # Testing testing
            app.db.command('ping')
            return jsonify({
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            return jsonify({
                "status": "unhealthy", 
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }), 500

    return app


# Helpers
def ensure_indexes(db):
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING)])
    db.pharmacies.create_index([("owner_id", ASCENDING)])
    db.pharmacies.create_index([("name", ASCENDING)])
    db.medicines.create_index([("name", ASCENDING)])
    db.medicines.create_index([("category", ASCENDING)])
    db.medicines.create_index([("pharmacy_id", ASCENDING)])
    db.orders.create_index([("user_id", ASCENDING)])
    db.orders.create_index([("status", ASCENDING)])
    db.orders.create_index([("created_at", DESCENDING)])
    db.reviews.create_index([("pharmacy_id", ASCENDING)])
    db.reviews.create_index([("user_id", ASCENDING)])
    db.schedules.create_index([("user_id", ASCENDING)])
    db.schedules.create_index([("created_at", DESCENDING)])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

def save_medicine_image(file):
    if not file:
        return None
    
    if file and allowed_file(file.filename):
        # Generate a unique filename using hash of original name and timestamp
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        hash_name = hashlib.md5(f"{name}{datetime.utcnow()}".encode()).hexdigest()
        new_filename = f"{hash_name}{ext}"
        
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
        file.save(file_path)
        
        # Return the relative path for database storage
        return f"images/medicines/{new_filename}"
    return None

def create_default_admin(db):
    # Check if admin user already exists
    admin_user = db.users.find_one({"email": "admin@medpanda.com"})
    
    if not admin_user:
        # Create default admin user
        hashed_password = generate_password_hash("admin123")
        admin_doc = {
            "name": "System Administrator",
            "email": "admin@medpanda.com",
            "password": hashed_password,
            "role": "admin",
            "created_at": datetime.utcnow(),
            "is_active": True,
        }
        result = db.users.insert_one(admin_doc)
        print(f"Default admin user created: admin@medpanda.com / admin123")
        print(f"Admin user ID: {result.inserted_id}")
    else:
        print(f"Admin user already exists: {admin_user['email']}")


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)