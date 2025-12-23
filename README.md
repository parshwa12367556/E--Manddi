# 🌱 Cropify - Agri-Marketing Platform

Cropify is a modern, user-friendly web application designed to bridge the gap between farmers and consumers. It provides a digital marketplace where farmers can sell their produce directly, and customers can buy fresh, high-quality products. The platform supports different user roles, product management, a shopping cart, and a feedback system.

## ✨ Features

- **Dual User Roles**: Users can register as either a **Buyer** or a **Seller**.
- **Product Catalog**: Browse products categorized into Fruits, Vegetables, Fertilizers, and Pesticides.
- **Product Management**: Sellers can add new products to the marketplace, specifying details like name, category, price, quantity, and an image URL.
- **Interactive Shopping Cart**: A client-side shopping cart allows users to add products, view their selections, and see the total cost before checkout.
- **User Authentication**: Secure registration and login functionality.
- **Feedback System**: Customers can submit feedback and ratings to help improve the service.
- **Admin Dashboard**: A dedicated dashboard for administrators to view registered users, recent feedback, and manage all products on the platform.
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

---

*This README was generated based on the project's HTML templates. The backend setup instructions are inferred and may need to be adjusted based on the actual implementation in `app.py`.*
Search Functionality:

Current State: Users can only filter by category.
Recommendation: Add a search bar to the navigation or product page so users can find products by name (e.g., "Tomato", "Urea").
Wishlist Implementation:

Current State: You have a Wishlist model defined in app.py, but there are no routes or templates to use it.
Recommendation: Add routes to add/remove items and a view to see the wishlist.
Buyer Order History:

Current State: Buyers see a confirmation page after purchase, but there is no "My Orders" page to view past purchases.
Recommendation: Create a route and template where buyers can track status and view history.
Seller Dashboard:

Current State: Sellers are redirected to the general product page upon login. They can add products but cannot edit or delete their own listings (only Admin can).
Recommendation: Create a dedicated dashboard for sellers to manage their inventory and view their specific earnings.
Shipping Address Management:

Current State: The Order model does not store a shipping address.
Recommendation: Add an address field to the Order model or the User profile and require it during checkout.
Product Reviews:

Current State: There is a general site Feedback system.
Recommendation: Add a review system linked to specific Products so buyers can rate the quality of specific items.
Password Reset:

Current State: No way to recover a lost password.
Recommendation: Implement a "Forgot Password" flow using email tokens.

Implement Template Inheritance
Problem: Your HTML files (index.html, product.html, admin.html, etc.) repeat the same code for the navbar, footer, and <head> section. This makes it difficult to update the site's layout, as you have to change every single file.
Solution: Create a single base.html file that contains the common structure (like the navbar and footer). Other templates can then use {% extends 'base.html' %} to inherit this structure and only provide the content specific to that page. This will dramatically reduce code duplication and make your project much easier to manage.
2. Add CSRF Protection to Forms
Problem: Your forms (login, registration, adding products) are currently vulnerable to a common web security vulnerability called Cross-Site Request Forgery (CSRF).
Solution: You can integrate the Flask-WTF library. It simplifies form creation and automatically adds CSRF protection with a hidden token in your forms, making your application much more secure.
3. Implement Backend-Powered Sorting for Products
Problem: The "Sort By" feature on your product.html page only sorts the products currently visible on that single page using JavaScript. It doesn't sort all products in the database.
Solution: Modify the product route in app.py to accept sorting parameters from the URL (e.g., ?sort=price_asc). Use these parameters to change the ORDER BY clause in your SQLAlchemy query, ensuring that sorting is accurate across all available products.
4. Add a "Change Password" Feature for Users
Problem: Users can register and reset a forgotten password, but there is no way for a logged-in user to change their current password from their profile page. This is a standard security feature.
Solution: Create a new "Change Password" page and link it from the user's profile. This would require a new route in app.py that verifies the user's old password before hashing and saving the new one.
5. Enable File Uploads for Product Images
Problem: Sellers must find and paste a URL for product images, which is inconvenient and can lead to broken image links.
Solution: Change the image input on the addproduct.html and seller_edit_product.html forms from a text field to a file input (<input type="file">). In app.py, you can then handle the file upload, save it to a static folder on your server, and store the filename in the database.
6. Enhance the Admin & Seller Dashboards with Modals
Problem: The admin and seller dashboards use basic JavaScript confirm() popups for deleting items and redirect to separate pages for editing. This user experience can feel dated.
Solution: Use Bootstrap Modals for both "Edit" and "Delete Confirmation" actions. This keeps the user on the same page and provides a much smoother and more modern interface, similar to what is already implemented in your admin_products.html page.
7. Create a User Dropdown Menu in the Navbar
Problem: As more links like "Profile", "My Orders", and "Dashboard" are added for logged-in users, the navigation bar can become crowded.
Solution: Group user-specific links ("Profile", "My Orders", "Dashboard", "Logout") into a single dropdown menu that appears when a user clicks on their name. This cleans up the navbar and organizes the navigation logically.
