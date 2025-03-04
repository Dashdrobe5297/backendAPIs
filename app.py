import uuid
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db
from flask_cors import CORS  # Import Flask-CORS
from nltk.sem.chat80 import items

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize Firebase Admin SDK with Realtime Database URL
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://dashdrobe-website-form-default-rtdb.firebaseio.com/'
})

users = {}
carts = {}
orders = {}
products = {}
riders = {}

# ---------------------- User APIs ----------------------

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a user with user ID and user type (customer, rider, or store_owner)."""
    data = request.get_json()
    user_id = str(uuid.uuid4())  # Generate unique user ID
    user_type = data.get('user_type')  # customer, rider, or store_owner

    if user_type not in ['customer', 'rider', 'store_owner']:
        return jsonify({"error": "Invalid user type"}), 400

    # Create the user data
    user_data = {
        'user_id': user_id,
        'user_type': user_type
    }

    # Store the user data in Firebase Realtime Database
    ref = db.reference('users')  # Refers to 'users' node
    ref.child(user_id).set(user_data)  # Save user under their unique ID

    return jsonify({"message": "User created successfully", "user_id": user_id}), 201

@app.route('/api/users', methods=['GET'])
def get_all_users():
    """Retrieve all users with their user_id and user_type."""
    # Reference to the 'users' node in Firebase
    ref = db.reference('users')

    # Fetch all user data from Firebase
    users_data = ref.get()  # This will return all the user data in the 'users' node

    if not users_data:
        return jsonify({"message": "No users found"}), 404

    return jsonify({"users": users_data}), 200

# ---------------------- Customer APIs ----------------------

@app.route('/api/products', methods=['GET'])
def get_all_products():
    """Retrieve all products."""
    ref = db.reference('products')
    products = ref.get()
    if not products:
        return jsonify({"error": "No products found"}), 404
    return jsonify(products), 200

@app.route('/api/products/id/<product_id>', methods=['GET'])
def get_product_by_id(product_id):
    """Retrieve a specific product by ID."""
    ref = db.reference(f'products/{product_id}')
    product = ref.get()
    if not product:
        return jsonify({"error": "Product not found"}), 404
    return jsonify({product_id: product}), 200

@app.route('/api/products/store/<store_name>', methods=['GET'])
def get_products_by_store(store_name):
    """Retrieve products from a specific store."""
    ref = db.reference('products')
    all_products = ref.get()
    result = {pid: product for pid, product in all_products.items() if product['store_name'] == store_name}
    if not result:
        return jsonify({"error": "No products found for this store"}), 404
    return jsonify(result), 200

@app.route('/api/cart/<user_id>/add_product', methods=['POST'])
def add_product_to_cart(user_id):
    """Add a specific product to the user's cart."""
    data = request.get_json()
    product_id = data.get('product_id')  # Unique product ID
    quantity = data.get('quantity')  # Quantity to add

    if not product_id or not quantity:
        return jsonify({"error": "Product ID and quantity are required"}), 400

    # Check if the user exists in the Firebase database
    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Initialize the cart if it doesn't exist
    cart_ref = db.reference(f'carts/{user_id}')
    cart_data = cart_ref.get() or []

    # Check if the product already exists in the cart
    existing_item = next((item for item in cart_data if item['product_id'] == product_id), None)

    if existing_item:
        # If product already exists, update the quantity
        existing_item['quantity'] += quantity
        message = f"Product {product_id} quantity updated in cart."
    else:
        # Add new product to cart
        cart_data.append({
            'product_id': product_id,
            'quantity': quantity
        })
        message = f"Product {product_id} added to cart."

    # Save the updated cart back to the database
    cart_ref.set(cart_data)
    return jsonify({"message": message, "cart": cart_data}), 201

@app.route('/api/cart/<user_id>', methods=['DELETE'])
def remove_from_cart(user_id):
    """Remove an item from the user's cart."""
    data = request.get_json()
    item_id = data.get('item_id')

    if user_id not in carts:
        return jsonify({"error": "Cart not found"}), 404

    cart = carts[user_id]
    cart = [item for item in cart if item['item_id'] != item_id]

    carts[user_id] = cart
    return jsonify({"message": "Item removed from cart successfully"}), 200

@app.route('/api/cart/<user_id>', methods=['GET'])
def get_cart(user_id):
    """Get the cart details for a user."""
    # Check if the user exists in the Firebase database
    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Fetch the cart data for the user from Firebase
    cart_ref = db.reference(f'carts/{user_id}')
    cart_data = cart_ref.get()

    if not cart_data:
        return jsonify({"error": "Cart not found"}), 404

    return jsonify({"cart": cart_data}), 200

@app.route('/api/order/<user_id>', methods=['POST'])
def create_order(user_id):
    """Create an order for the user."""
    # Fetch the user from the Firebase database
    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Fetch the user's cart from the database
    cart_ref = db.reference(f'carts/{user_id}')
    cart_data = cart_ref.get()

    if not cart_data:
        return jsonify({"error": "Cart is empty"}), 400

    # Check product availability and adjust stock
    for item in cart_data:
        product_id = item['product_id']
        quantity_in_cart = item['quantity']

        # Fetch the product details from the database
        product_ref = db.reference(f'products/{product_id}')
        product_data = product_ref.get()

        if not product_data:
            return jsonify({"error": f"Product {product_id} not found"}), 404

        available_stock = product_data['stock']

        # Check if enough stock is available
        if available_stock < quantity_in_cart:
            return jsonify({"error": f"Not enough stock for product {product_id}. Available stock: {available_stock}"}), 400

        # Update the product stock in the database
        new_stock = available_stock - quantity_in_cart
        product_ref.update({'stock': new_stock})

    # Create an order
    order_id = str(uuid.uuid4())  # Generate unique order ID
    order_details = {
        'order_id': order_id,
        'user_id': user_id,
        'user_type': user_data['user_type'],
        'items': cart_data,  # Copy the cart items
        'status': 'pending'  # Initial order status
    }

    # Store the order in the database
    order_ref = db.reference(f'orders/{order_id}')
    order_ref.set(order_details)

    # Clear the user's cart in the database
    cart_ref.delete()

    return jsonify({"message": "Order placed successfully", "order_id": order_id}), 201

@app.route('/api/order/<user_id>', methods=['GET'])
def get_user_orders(user_id):
    """Get the orders placed by the user."""
    # Fetch the user from the Firebase database
    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Fetch all orders from the database
    orders_ref = db.reference('orders')
    all_orders = orders_ref.get()

    # Filter orders for the specific user
    user_orders = [
        order for order in all_orders.values() if order['user_id'] == user_id
    ] if all_orders else []

    if not user_orders:
        return jsonify({"message": "No orders found for this user"}), 404

    return jsonify(user_orders), 200

# ---------------------- Store Owner APIs ----------------------

@app.route('/api/products', methods=['POST'])
def add_product():
    """Add a new product or update quantity if the product exists in the products database."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is empty"}), 400

    product_name = data.get('name')
    product_description = data.get('description')
    product_price = data.get('price')
    product_image_url = data.get('image_url')
    store_name = data.get('store_name')
    quantity_to_add = data.get('stock', 1)  # Assuming the quantity to add is passed as stock

    if not all([product_name, product_description, product_price, product_image_url, store_name]):
        return jsonify({"error": "Missing required fields"}), 400


    # Check if product already exists in the products database
    ref = db.reference('products')
    products = ref.get()

    if products:  # Only iterate if products exist
        for product_id, product in products.items():
            # Check if product matches based on name, description, price, image_url, and store_name
            if (product.get('name') == product_name and
                    product.get('description') == product_description and
                    product.get('price') == product_price and
                    product.get('image_url') == product_image_url and
                    product.get('store_name') == store_name):
                # Update the stock/quantity of the existing product by adding the new stock
                new_stock = product.get('stock', 0) + quantity_to_add
                ref.child(product_id).update({'stock': new_stock})
                return jsonify({"message": "Product quantity updated", "product_id": product_id}), 200

    # If product does not exist, add it as a new product
    product_ref = ref.push()
    product_ref.set(data)

    return jsonify({"message": "Product added successfully", "product_id": product_ref.key}), 201

@app.route('/api/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    """Update an existing product."""
    data = request.get_json()
    ref = db.reference(f'products/{product_id}')
    ref.update(data)
    return jsonify({"message": "Product updated successfully"}), 200

@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete a product."""
    ref = db.reference(f'products/{product_id}')
    ref.delete()
    return jsonify({"message": "Product deleted successfully"}), 200

@app.route('/api/order/<order_id>/review', methods=['POST'])
def review_order(order_id):
    """Store owner reviews the order and either accepts or rejects it."""
    data = request.get_json()
    store_owner_id = data.get('store_owner_id')  # Store owner ID to authenticate the request
    decision = data.get('decision')  # "accept" or "reject"

    if decision not in ['accept', 'reject']:
        return jsonify({"error": "Invalid decision. Choose 'accept' or 'reject'."}), 400

    # Fetch the order from Firebase Realtime Database
    ref = db.reference(f'orders/{order_id}')
    order_data = ref.get()

    if order_data is None:
        return jsonify({"error": "Order not found"}), 404

    # Check if the order is already processed
    if order_data.get('status') != 'pending':
        return jsonify({"error": "Order already processed. Cannot review."}), 400

    # Validate the store owner ID in the users data
    users_ref = db.reference('users')
    users = users_ref.get()

    store_owner_valid = False
    for user_id, user_data in users.items():
        if user_id == store_owner_id and user_data.get('user_type') == 'store_owner':
            store_owner_valid = True
            break

    if not store_owner_valid:
        return jsonify({"error": "Invalid store owner. User not found or unauthorized."}), 403

    # Check the quantity of items in the order
    if 'items' not in order_data or len(order_data['items']) == 0:
        return jsonify({"error": "Order has no items."}), 400

    total_quantity = sum(item.get('quantity', 0) for item in order_data['items'])

    # Update the order status based on the decision
    new_status = 'accepted' if decision == 'accept' else 'rejected'
    ref.update({'status': new_status})

    if new_status == 'accepted':
        # Update the accepted order in the accepted_orders database with the same order_id
        accepted_orders_ref = db.reference(f'accepted_orders/{order_id}')

        # Prepare the order details to be added to the accepted orders database
        accepted_order_data = {
            'order_id': order_id,
            'store_owner_id': store_owner_id,
            'items': order_data['items'],  # Keep the order items
            'total_quantity': total_quantity,
            'status': 'accepted',
            'timestamp': order_data.get('timestamp')  # Optionally, you can include the timestamp
        }

        # Store or update the accepted order in the database
        accepted_orders_ref.set(accepted_order_data)

    return jsonify({
        "message": f"Order {new_status} successfully. Total items: {total_quantity}",
        "order_id": order_id
    }), 200

# ---------------------- Rider APIs ----------------------

@app.route('/api/orders/available_for_riders', methods=['GET'])
def get_available_orders_for_riders():
    """Retrieve all accepted orders that can be delivered by any rider."""
    available_orders = []

    # Fetch all accepted orders from Firebase
    accepted_orders_ref = db.reference('accepted_orders')
    accepted_orders_data = accepted_orders_ref.get()

    if not accepted_orders_data:
        return jsonify({"message": "No accepted orders available for delivery."}), 404

    # Fetch all products from the products node
    products_ref = db.reference('products')
    products_data = products_ref.get()

    if not products_data:
        return jsonify({"error": "No products found."}), 404

    # Iterate through accepted orders and prepare the response
    for order_id, order_details in accepted_orders_data.items():
        # Initialize total price
        total_price = 0

        # Ensure the items list exists and has the necessary fields
        if 'items' in order_details:
            for item in order_details['items']:
                product_id = item.get('product_id')

                # Check if product_id exists in the products node
                product = products_data.get(product_id)
                if product:
                    price = product.get('price', 0)  # Default to 0 if price is missing
                    quantity = item.get('quantity', 0)  # Default to 0 if quantity is missing
                    total_price += price * quantity
                else:
                    # Handle case where product is not found in products data
                    return jsonify({"error": f"Product with ID {product_id} not found."}), 404

        available_orders.append({
            "order_id": order_id,
            "store_owner_id": order_details.get('store_owner_id'),
            "items": order_details.get('items'),
            "total_price": total_price,
            "status": order_details.get('status')
        })

    return jsonify(available_orders), 200

@app.route('/api/orders/<order_id>/accept', methods=['POST'])
def accept_order_for_delivery(order_id):
    """Rider accepts an order for delivery and updates their profile."""
    data = request.get_json()
    rider_id = data.get('rider_id')

    # Fetch the rider from the users node to validate the rider_id
    users_ref = db.reference('users')
    users = users_ref.get()

    rider_valid = False
    for user_id, user_data in users.items():
        if user_id == rider_id and user_data.get('user_type') == 'rider':
            rider_valid = True
            break

    if not rider_valid:
        return jsonify({"error": "Invalid rider ID. User not found or unauthorized."}), 403

    # Fetch the order from the accepted_orders node
    accepted_orders_ref = db.reference(f'accepted_orders/{order_id}')
    order = accepted_orders_ref.get()

    if not order:
        return jsonify({"error": "Order not found in accepted orders."}), 404

    if order['status'] != 'accepted':
        return jsonify({"error": "Order is not available for delivery."}), 400

    # Assign the order to the rider and update the order status to 'on the way'
    order['rider_id'] = rider_id
    order['status'] = 'on the way'  # Change the status to 'on the way'

    # Update the order status in the accepted_orders node
    accepted_orders_ref.update(order)

    # Update the order status in the main orders node as well
    orders_ref = db.reference(f'orders/{order_id}')
    orders_ref.update({'status': 'on the way', 'rider_id': rider_id})

    # Fetch the rider's orders from the 'users' node
    rider_orders_ref = db.reference(f'users/{rider_id}/assigned_orders')
    rider_orders = rider_orders_ref.get()

    if rider_orders is None:
        rider_orders = []

    rider_orders.append(order_id)

    # Update the rider's assigned orders
    rider_orders_ref.set(rider_orders)

    return jsonify({"message": "Order accepted for delivery", "order_id": order_id}), 200

@app.route('/api/rider/<rider_id>/orders', methods=['GET'])
def get_rider_orders(rider_id):
    """Get all orders assigned to the rider."""
    # Fetch the users data to validate the rider_id
    users_ref = db.reference('users')
    users = users_ref.get()

    rider_profile = None
    for user_data in users.values():
        if user_data.get('user_id') == rider_id and user_data.get('user_type') == 'rider':
            rider_profile = user_data
            break

    if not rider_profile:
        return jsonify({"error": "Rider not found or unauthorized."}), 404

    # Assuming the rider's assigned orders are stored in a structure like this in the profile
    rider_orders = []
    for order_id in rider_profile.get('assigned_orders', []):
        order_ref = db.reference(f'orders/{order_id}')
        order = order_ref.get()
        if order:
            total_price = 0
            order_items = []

            # Loop through the order items to fetch their prices from the products node
            for item in order.get('items', []):
                product_id = item.get('product_id')
                if product_id:
                    product_ref = db.reference(f'products/{product_id}')
                    product = product_ref.get()

                    # If product exists, calculate price
                    if product:
                        price = product.get('price', 0)
                        item['price'] = price  # Update the price in the item
                        total_price += price * item['quantity']  # Calculate total price for the item
                        order_items.append(item)
                    else:
                        return jsonify({"error": f"Product with id {product_id} not found."}), 404
                else:
                    return jsonify({"error": "Product ID missing in order item."}), 400

            rider_orders.append({
                "order_id": order_id,
                "user_id": order.get('user_id'),
                "status": order.get('status'),
                "items": order_items,
                "total_price": total_price,
            })

    if not rider_orders:
        return jsonify({"message": "No orders assigned to the rider."}), 404

    return jsonify(rider_orders), 200

@app.route('/api/orders/<order_id>/deliver', methods=['POST'])
def mark_order_as_delivered(order_id):
    """Mark the order as delivered by the rider."""
    data = request.get_json()
    rider_id = data.get('rider_id')

    # Fetch the users data to validate the rider_id
    users_ref = db.reference('users')
    users = users_ref.get()

    rider_profile = None
    for user_data in users.values():
        if user_data.get('user_id') == rider_id and user_data.get('user_type') == 'rider':
            rider_profile = user_data
            break

    if not rider_profile:
        return jsonify({"error": "Rider not found or unauthorized."}), 404

    # Fetch the order from the orders node
    order_ref = db.reference(f'orders/{order_id}')
    order = order_ref.get()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    # Fetch the corresponding order from the accepted_orders node
    accepted_order_ref = db.reference(f'accepted_orders/{order_id}')
    accepted_order = accepted_order_ref.get()
    if not accepted_order:
        return jsonify({"error": "Order not found in accepted orders"}), 404

    # Check if the order was assigned to the rider
    if order.get('rider_id') != rider_id:
        return jsonify({"error": "This order is not assigned to the rider."}), 400

    # Check if both the orders' statuses are 'on the way'
    if order['status'] != 'on the way' or accepted_order['status'] != 'on the way':
        return jsonify({"error": "Order is not 'on the way'. Cannot mark as delivered."}), 400

    # Update the status of both the orders and accepted_orders to 'delivered'
    order_ref.update({'status': 'delivered'})
    accepted_order_ref.update({'status': 'delivered'})

    # Update the rider's order status to 'delivered' as well
    rider_profile_ref = db.reference(f'users/{rider_id}')
    if rider_profile_ref:
        # Ensure that the order is in the rider's assigned orders
        if order_id in rider_profile.get('assigned_orders', []):
            rider_profile_ref.update({
                'assigned_orders': [order for order in rider_profile.get('assigned_orders', []) if order != order_id],
                'completed_orders': rider_profile.get('completed_orders', []) + [order_id]
            })

    return jsonify({"message": "Order marked as delivered", "order_id": order_id}), 200

# ---------------------- Driver ----------------------

if __name__ == '__main__':
    app.run(debug=True)
