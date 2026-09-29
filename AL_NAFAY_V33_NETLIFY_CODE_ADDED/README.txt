AL NAFAY V33 - Mobile style + Owner login

1. Double-click run.bat.
2. Customer website:  http://localhost:5000/
3. Owner dashboard:   http://localhost:5000/admin   (password required)

ADMIN PASSWORD
- First run: the password is shown in the black window and saved in admin_password.txt.
- To change it: open admin_password.txt, type a new password, save, restart run.bat.
- Online server: you can also set it with the ALNAFAY_ADMIN_PASSWORD environment variable.
- 5 wrong attempts lock login for 5 minutes. Logout button is at the top right of the dashboard.
- Never share admin_password.txt or secret.key.

WHAT IS PUBLIC / PRIVATE
- Public: website, product list, store contact info, placing an order.
- Private (login needed): orders, customers, adding/editing/deleting products, prices, stock, order status, settings.

ORDERS
- One customer checkout = one order, even with several Thaan/Suit items. Items are listed inside the order in the dashboard.

PRODUCT PHOTOS
- Upload up to 4 photos per product. Each is cropped to a centered square (1000x1000) so cards look equal. Take fabric photos roughly square.

Server settings (optional environment variables): PORT, ALNAFAY_DB (database file path), ALNAFAY_ADMIN_PASSWORD.
