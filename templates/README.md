# 🌱E-Mandi - Online Marketplace Platform

Cropify is a modern, user-friendly web application designed to bridge the gap between farmers and consumers. It provides a digital marketplace where farmers can sell their produce directly, and customers can buy fresh, high-quality products. The platform supports different user roles, product management, a shopping cart, and a feedback system.

## ✨ Features

- **Dual User Roles**: Users can register as either a **Buyer** or a **Seller**.
- **Product Catalog**: Browse products categorized into Fruits, Vegetables, Fertilizers, and Pesticides.
- **Product Management**: Sellers can add new products to the marketplace, specifying details like name, category, price, quantity, and an image URL.
- **Interactive Shopping Cart**: A client-side shopping cart allows users to add products, view their selections, and see the total cost before checkout.
- **User Authentication**: Secure registration and login functionality.
- **Feedback System**: Customers can submit feedback and ratings to help improve the service.
- **Admin Dashboard**: A dedicated dashboard for administrators to view registered users, recent feedback, and manage all products on the platform.
- **Logistics Margin System**: Built-in system to calculate and track profits from delivery operations (Shipping Fee vs Delivery Cost).
- **Responsive Design**: Built with Bootstrap 5, the UI is fully responsive and works seamlessly on desktops, tablets, and mobile devices.

## 🛠️ Tech Stack

The project is built with a classic web development stack:

- **Frontend**:
  - HTML5
  - CSS3 with Bootstrap 5 for styling and responsiveness.
  - JavaScript for dynamic client-side functionality, including cart management and API interactions.
- **Backend (Inferred)**:
  - **Python** with the **Flask** web framework.
  - A relational database like **SQLite** or **PostgreSQL** for data persistence.

## 📂 Project Structure

The project follows a standard Flask application structure.

```
mini project/
├── templates/         # HTML templates for all pages
│   ├── index.html
│   ├── product.html
│   ├── addproduct.html
│   ├── cart.html
│   ├── login.html
│   ├── register.html
│   ├── feedback.html
│   ├── thankyou.html
│   └── admin.html
├── static/            # (Assumed) For CSS, JS, and image assets
├── app.py             # (Assumed) Main Flask application file
├── requirements.txt   # (Assumed) Python dependencies
└── README.md          # Project documentation
```

## 🚀 Getting Started

Follow these instructions to get a local copy of the project up and running for development and testing purposes.

### Prerequisites

- Python 3.8+
- `pip` (Python package installer)

### Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/cropify.git
    cd cropify
    ```

2.  **Create and activate a virtual environment:**
    ```sh
    # For Windows
    python -m venv venv
    .\venv\Scripts\activate

    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required packages:**
    *(You will need to create a `requirements.txt` file containing `Flask` and any other necessary libraries).*
    ```sh
    pip install -r requirements.txt
    ```

4.  **Set up the database:**
    *(This assumes you have a function in your `app.py` to initialize the database).*
    ```sh
    # This command may vary based on your implementation
    flask init-db
    ```

5.  **Run the application:**
    ```sh
    flask run
    ```

The application will be available at `http://127.0.0.1:5000`.

## ⚙️ API Endpoints

The frontend communicates with the Flask backend via the following API endpoints:

- `POST /api/register`: Registers a new user.
- `POST /api/login`: Authenticates and logs in a user.
- `GET /api/products`: Fetches a list of all available products.
- `POST /api/products`: Adds a new product to the database.
- `POST /api/feedback`: Submits user feedback.

## 📖 How to Use

1.  **Register an Account**: Navigate to the Register page and sign up as a "Buyer" or "Seller".
2.  **Login**: Use your credentials to log in.
3.  **Browse Products**: Go to the Products page to see all available items.
4.  **Add to Cart**: Click the "Add to Cart" button on any product to add it to your shopping cart. The cart count in the navigation bar will update automatically.
5.  **View Cart**: Click on the Cart link in the navigation to review your items and total price.
6.  **Add a Product (Sellers)**: If registered as a seller, you can navigate to the "Add New Product" page to list your items for sale.

## 🚚 Delivery & Logistics Margin System

The platform implements a profit margin system for logistics:

### Workflow
1.  **Configuration**: Admin configures `Shipping Fee` (Customer Charge) and `Delivery Partner Cost` (Expense) in settings.
2.  **Calculation**:
    - **Revenue**: Customer pays the shipping fee (e.g., ₹60).
    - **Cost**: Platform owes the delivery partner (e.g., ₹45).
    - **Profit**: The difference (₹15) is retained as platform earnings.
3.  **Free Shipping**: Orders above a specific threshold (e.g., ₹600) get free shipping. In this case, the platform absorbs the delivery cost.

### Real-World Example
- **Customer Order**: ₹400 (Below free shipping threshold)
- **Shipping Fee Charged**: ₹60
- **Delivery Partner Cost**: ₹45
- **Net Profit**: ₹60 - ₹45 = **₹15**

---

*This README was generated based on the project's HTML templates. The backend setup instructions are inferred and may need to be adjusted based on the actual implementation in `app.py`.*

3. Buyer Experience
These features are common in e-commerce sites and can significantly increase user engagement and sales.

Product Wishlist:

What it is: Allow buyers to save products they are interested in to a "Wishlist" to purchase later.
Why it's important: This encourages return visits and can lead to future sales. It also provides you with valuable data on what products are popular, even if they aren't being purchased immediately.
More Detailed Order Tracking:

What it is: On the "My Orders" page, expand the status tracker to include timestamps for each status change (e.g., "Confirmed on Nov 2, 10:30 AM", "Shipped on Nov 3, 4:00 PM").
Why it's important: This gives customers more precise information and a better sense of where their order is, improving their post-purchase experience.
4. Admin & Operational Features
These will make managing the platform easier and more secure.

Seller/Farmer Approval System:

What it is: When a new user registers as a "farmer" or "seller", their account is initially set to a "pending" state. An admin must manually approve their account before they can start adding products.
Why it's important: This gives you control over who can sell on your platform, allowing you to vet sellers and maintain a higher standard of quality and trust.
Expanded Notifications:

What it is: Use the send_sms or an email function to automatically notify users at key moments.
Why it's important: Good communication is key to a great service.
Examples:
Notify a seller when one of their products has been sold.
Notify a buyer via SMS when their order status changes to "Shipped" or "Delivered".
Send an email to a farmer when a payout has been processed for them.

2. Seller & Farmer Experience
Improving the tools for your sellers will keep them engaged and happy.

Seller Payout History:

What it is: A new section in the Seller Dashboard where farmers can see their own payout history, including dates, amounts paid, and transaction references.
Why it's important: This provides transparency and builds trust. Farmers can track their earnings and see exactly when they were paid, reducing the need to contact the admin for inquiries.
Product Image Uploads:

What it is: Instead of asking sellers to provide an image URL, implement a feature that allows them to directly upload image files from their computer or phone.
Why it's important: This is a major user experience improvement. Most sellers will not have their product images hosted online, so a file upload system is much more practical and user-friendly.

Can you also update the footer to match this new modern green theme?

How can I add a search bar to the product list header?

Can you also apply the distance-based fee logic to the Razorpay online payment method?

How can I make the distance-based shipping fee update dynamically on the checkout page as I type?