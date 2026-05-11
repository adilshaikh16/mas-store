import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials

# ========== PAGE CONFIGURATION ==========
st.set_page_config(
    page_title="MAS Store - Complete Business Software",
    page_icon="🏬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== INITIALIZE SESSION STATE ==========
if 'transaction_log' not in st.session_state:
    st.session_state.transaction_log = pd.DataFrame(columns=[
        'Date', 'Type', 'Product', 'Quantity', 'Unit_Cost', 'Total_Cost', 
        'Unit_Price', 'Total_Price', 'Profit_Loss', 'Notes'
    ])

if 'inventory' not in st.session_state:
    st.session_state.inventory = pd.DataFrame(columns=[
        'Product', 'Quantity', 'Avg_Cost_Price'
    ])

# ========== MODULAR FUNCTIONS ==========
def add_purchase(product, quantity, cost_price, notes=""):
    """Record a purchase"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Update inventory
    if product in st.session_state.inventory['Product'].values:
        idx = st.session_state.inventory[st.session_state.inventory['Product'] == product].index[0]
        old_qty = st.session_state.inventory.at[idx, 'Quantity']
        old_avg_cost = st.session_state.inventory.at[idx, 'Avg_Cost_Price']
        new_qty = old_qty + quantity
        new_avg_cost = ((old_avg_cost * old_qty) + (cost_price * quantity)) / new_qty
        st.session_state.inventory.at[idx, 'Quantity'] = new_qty
        st.session_state.inventory.at[idx, 'Avg_Cost_Price'] = new_avg_cost
    else:
        new_row = pd.DataFrame([[product, quantity, cost_price]], 
                               columns=['Product', 'Quantity', 'Avg_Cost_Price'])
        st.session_state.inventory = pd.concat([st.session_state.inventory, new_row], ignore_index=True)
    
    # Add to transaction log
    new_transaction = pd.DataFrame([[timestamp, 'Purchase', product, quantity, cost_price, 
                                    cost_price * quantity, 0, 0, 0, notes]],
                                   columns=['Date', 'Type', 'Product', 'Quantity', 'Unit_Cost', 
                                           'Total_Cost', 'Unit_Price', 'Total_Price', 'Profit_Loss', 'Notes'])
    st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, new_transaction], 
                                                 ignore_index=True)
    return True

def add_sale(product, quantity, selling_price, notes=""):
    """Record a sale and calculate profit"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check inventory
    if product not in st.session_state.inventory['Product'].values:
        return False, "Product not found in inventory!"
    
    idx = st.session_state.inventory[st.session_state.inventory['Product'] == product].index[0]
    current_stock = st.session_state.inventory.at[idx, 'Quantity']
    if quantity > current_stock:
        return False, f"Insufficient stock! Available: {current_stock}"
    
    # Calculate profit
    avg_cost = st.session_state.inventory.at[idx, 'Avg_Cost_Price']
    total_cost = avg_cost * quantity
    total_revenue = selling_price * quantity
    profit_loss = total_revenue - total_cost
    
    # Update inventory
    new_qty = current_stock - quantity
    st.session_state.inventory.at[idx, 'Quantity'] = new_qty
    
    # Add to transaction log
    new_transaction = pd.DataFrame([[timestamp, 'Sale', product, quantity, avg_cost, total_cost,
                                    selling_price, total_revenue, profit_loss, notes]],
                                   columns=['Date', 'Type', 'Product', 'Quantity', 'Unit_Cost',
                                           'Total_Cost', 'Unit_Price', 'Total_Price', 'Profit_Loss', 'Notes'])
    st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, new_transaction],
                                                 ignore_index=True)
    return True, f"Sale recorded! Profit: ₹{profit_loss:,.2f}"

def add_expense_withdrawal(amount, category, notes=""):
    """Record expense or withdrawal"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_transaction = pd.DataFrame([[timestamp, category, '', 0, 0, amount, 0, 0, -amount, notes]],
                                   columns=['Date', 'Type', 'Product', 'Quantity', 'Unit_Cost',
                                           'Total_Cost', 'Unit_Price', 'Total_Price', 'Profit_Loss', 'Notes'])
    st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, new_transaction],
                                                 ignore_index=True)
    return True

def export_to_csv():
    """Export transaction log to CSV"""
    csv = st.session_state.transaction_log.to_csv(index=False)
    return csv

def export_to_google_sheets():
    """Export data to Google Sheets"""
    try:
        SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', SCOPES)
        client = gspread.authorize(creds)
        
        # Try to open existing sheet or create new
        try:
            sheet = client.open('MAS_Store_Backup')
        except:
            sheet = client.create('MAS_Store_Backup')
            
        # Update inventory sheet
        try:
            inventory_worksheet = sheet.worksheet('Inventory')
        except:
            inventory_worksheet = sheet.add_worksheet(title='Inventory', rows=1000, cols=10)
        inventory_worksheet.clear()
        inventory_worksheet.update([st.session_state.inventory.columns.values.tolist()] + 
                                   st.session_state.inventory.values.tolist())
        
        # Update transactions sheet
        try:
            trans_worksheet = sheet.worksheet('Transactions')
        except:
            trans_worksheet = sheet.add_worksheet(title='Transactions', rows=1000, cols=20)
        trans_worksheet.clear()
        trans_worksheet.update([st.session_state.transaction_log.columns.values.tolist()] + 
                              st.session_state.transaction_log.values.tolist())
        
        return True, "Successfully synced to Google Sheets!"
    except Exception as e:
        return False, f"Error: {str(e)}"

def backup_to_google_drive():
    """Backup all data to Google Drive"""
    try:
        # Export current data to CSV files
        inventory_csv = st.session_state.inventory.to_csv(index=False)
        transactions_csv = st.session_state.transaction_log.to_csv(index=False)
        
        # Save temporarily
        inventory_path = "inventory_backup.csv"
        transactions_path = "transactions_backup.csv"
        with open(inventory_path, 'w') as f:
            f.write(inventory_csv)
        with open(transactions_path, 'w') as f:
            f.write(transactions_csv)
        
        # Authenticate and upload to Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = Credentials.from_service_account_file('creds.json', scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Create backup folder
        query = "name='MAS_Store_Backups' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_service.files().list(q=query, spaces='drive').execute()
        folder_id = None
        for item in results.get('files', []):
            folder_id = item['id']
        
        if not folder_id:
            folder_metadata = {'name': 'MAS_Store_Backups', 'mimeType': 'application/vnd.google-apps.folder'}
            folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder['id']
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Upload inventory backup
        file_inventory = drive_service.files().create(body={'name': f'inventory_{timestamp}.csv', 'parents': [folder_id]},
                                                      media_body=MediaFileUpload(inventory_path, mimetype='text/csv')).execute()
        
        # Upload transactions backup
        file_transactions = drive_service.files().create(body={'name': f'transactions_{timestamp}.csv', 'parents': [folder_id]},
                                                         media_body=MediaFileUpload(transactions_path, mimetype='text/csv')).execute()
        
        # Clean up local files
        os.remove(inventory_path)
        os.remove(transactions_path)
        
        return True, f"Backup complete! Backup ID: {file_inventory['id']}"
    except Exception as e:
        return False, f"Backup failed: {str(e)}"

# ========== CUSTOM SIDEBAR MENU ==========
# Using standard Streamlit sidebar menu for reliability
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/shop.png", width=80)
    st.markdown("# 🏬 MAS Store")
    st.markdown("---")
    menu_option = st.radio(
        "Navigate",
        ["📊 Dashboard", "🛒 Purchase", "💵 Sale", "💰 Profit/Loss", "📝 Expenses & Withdrawals", 
         "📜 Transaction Log", "☁️ Cloud Backup", "ℹ️ About"],
        index=0
    )
    st.markdown("---")
    st.caption(f"Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ========== MAIN PAGE RENDERING ==========
st.title("🏬 MAS Store - Complete Business Management System")

if menu_option == "📊 Dashboard":
    # Display financial metrics
    st.subheader("Financial Dashboard")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    # Calculate metrics
    total_purchases = st.session_state.transaction_log[st.session_state.transaction_log['Type'] == 'Purchase']['Total_Cost'].sum()
    total_sales = st.session_state.transaction_log[st.session_state.transaction_log['Type'] == 'Sale']['Total_Price'].sum()
    total_profit = st.session_state.transaction_log['Profit_Loss'].sum()
    total_expenses = st.session_state.transaction_log[st.session_state.transaction_log['Type'].isin(['Expense', 'Withdrawal'])]['Total_Cost'].sum()
    net_profit = total_profit - total_expenses
    
    with col1:
        st.metric("💰 Total Purchases", f"₹{total_purchases:,.2f}")
    with col2:
        st.metric("💸 Total Sales", f"₹{total_sales:,.2f}")
    with col3:
        st.metric("📈 Gross Profit", f"₹{total_profit:,.2f}")
    with col4:
        st.metric("📉 Expenses", f"₹{total_expenses:,.2f}")
    with col5:
        st.metric("🎯 Net Profit", f"₹{net_profit:,.2f}")
    
    # Inventory Summary
    st.subheader("📦 Inventory Summary")
    if not st.session_state.inventory.empty:
        cols = st.columns(4)
        for idx, (_, row) in enumerate(st.session_state.inventory.iterrows()):
            with cols[idx % 4]:
                st.info(f"**{row['Product']}**\n\nStock: {row['Quantity']} units\nAvg Cost: ₹{row['Avg_Cost_Price']:,.2f}")
    else:
        st.warning("No products in inventory.")
    
    # Profit/Loss Chart
    if not st.session_state.transaction_log.empty:
        st.subheader("📊 Profit/Loss Over Time")
        daily_pnl = st.session_state.transaction_log.groupby(st.session_state.transaction_log['Date'].dt.date)['Profit_Loss'].sum().reset_index()
        fig = px.line(daily_pnl, x='Date', y='Profit_Loss', title='Daily Profit/Loss Trend')
        st.plotly_chart(fig, use_container_width=True)

elif menu_option == "🛒 Purchase":
    st.subheader("Record New Purchase")
    
    with st.form("purchase_form"):
        col1, col2 = st.columns(2)
        with col1:
            product = st.text_input("Product Name")
            quantity = st.number_input("Quantity", min_value=1, step=1)
        with col2:
            cost_price = st.number_input("Cost Price (₹)", min_value=0.01, step=10.00)
            notes = st.text_area("Notes (Optional)")
        
        submitted = st.form_submit_button("📥 Record Purchase")
        if submitted and product and quantity and cost_price:
            add_purchase(product, int(quantity), cost_price, notes)
            st.success(f"Purchase recorded: {quantity} x {product} @ ₹{cost_price} each")
            st.balloons()
        elif submitted:
            st.error("Please fill all required fields.")

elif menu_option == "💵 Sale":
    st.subheader("Record Sale")
    
    if st.session_state.inventory.empty:
        st.warning("No products in inventory. Please add purchases first.")
    else:
        with st.form("sale_form"):
            col1, col2 = st.columns(2)
            with col1:
                product = st.selectbox("Product", st.session_state.inventory['Product'].tolist())
                quantity = st.number_input("Quantity", min_value=1, step=1)
            with col2:
                selling_price = st.number_input("Selling Price (₹)", min_value=0.01, step=10.00)
                notes = st.text_area("Notes (Optional)")
            
            submitted = st.form_submit_button("💰 Record Sale")
            if submitted:
                success, message = add_sale(product, quantity, selling_price, notes)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)

elif menu_option == "💰 Profit/Loss":
    st.subheader("Profit & Loss Analysis")
    
    if not st.session_state.transaction_log.empty:
        # Filter data
        transaction_types = st.multiselect("Filter by Transaction Type", 
                                           st.session_state.transaction_log['Type'].unique(),
                                           default=st.session_state.transaction_log['Type'].unique())
        filtered_data = st.session_state.transaction_log[st.session_state.transaction_log['Type'].isin(transaction_types)]
        
        # Summary statistics
        col1, col2, col3 = st.columns(3)
        total_profit = filtered_data['Profit_Loss'].sum()
        total_revenue = filtered_data[filtered_data['Type'] == 'Sale']['Total_Price'].sum()
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        with col1:
            st.metric("Total Profit/Loss", f"₹{total_profit:,.2f}")
        with col2:
            st.metric("Total Revenue", f"₹{total_revenue:,.2f}")
        with col3:
            st.metric("Profit Margin", f"{profit_margin:.2f}%")
        
        # Profit by product
        st.subheader("Profit by Product")
        product_profit = filtered_data[filtered_data['Type'] == 'Sale'].groupby('Product')['Profit_Loss'].sum().sort_values(ascending=False)
        fig = px.bar(product_profit, x=product_profit.index, y=product_profit.values, title='Profit by Product')
        st.plotly_chart(fig, use_container_width=True)
        
        # Detailed breakdown
        st.subheader("Detailed Transaction View")
        st.dataframe(filtered_data, use_container_width=True)
        
        # Export option
        st.download_button("📥 Download Report as CSV", export_to_csv(), file_name=f"pnl_report_{datetime.now().strftime('%Y%m%d')}.csv")
    else:
        st.warning("No transactions recorded yet.")

elif menu_option == "📝 Expenses & Withdrawals":
    st.subheader("Record Expense or Withdrawal")
    
    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount (₹)", min_value=0.01, step=100.00)
            category = st.selectbox("Category", ["Expense", "Withdrawal", "Rent", "Salary", "Utility", "Other"])
        with col2:
            notes = st.text_area("Description/Notes")
        
        submitted = st.form_submit_button("Record Transaction")
        if submitted and amount:
            add_expense_withdrawal(amount, category, notes)
            st.success(f"{category} recorded: ₹{amount}")
        elif submitted:
            st.error("Please enter amount.")

elif menu_option == "📜 Transaction Log":
    st.subheader("Complete Transaction History")
    
    if not st.session_state.transaction_log.empty:
        # Display log
        st.dataframe(st.session_state.transaction_log, use_container_width=True)
        
        # Filters
        st.subheader("Filter Transactions")
        col1, col2 = st.columns(2)
        with col1:
            transaction_type = st.selectbox("Transaction Type", ['All'] + st.session_state.transaction_log['Type'].unique().tolist())
        with col2:
            date_range = st.date_input("Date Range", [])
        
        # Apply filters
        filtered = st.session_state.transaction_log
        if transaction_type != 'All':
            filtered = filtered[filtered['Type'] == transaction_type]
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered['Date'] = pd.to_datetime(filtered['Date'])
            filtered = filtered[(filtered['Date'].dt.date >= start_date) & (filtered['Date'].dt.date <= end_date)]
        
        st.dataframe(filtered, use_container_width=True)
        
        # Export button
        st.download_button("📥 Download CSV", export_to_csv(), file_name=f"transactions_{datetime.now().strftime('%Y%m%d')}.csv")
    else:
        st.info("No transactions recorded yet. Start by adding a purchase or sale!")

elif menu_option == "☁️ Cloud Backup":
    st.subheader("Cloud Sync & Backup")
    
    st.markdown("### Google Sheets Sync")
    st.caption("Sync your data to Google Sheets for cloud access")
    if st.button("☁️ Sync to Google Sheets"):
        with st.spinner("Syncing to Google Sheets..."):
            success, message = export_to_google_sheets()
            if success:
                st.success(message)
            else:
                st.error(message)
    
    st.markdown("---")
    st.markdown("### Google Drive Backup")
    st.caption("Create a manual backup of all data to Google Drive")
    if st.button("💾 Manual Backup to Drive"):
        with st.spinner("Creating backup..."):
            success, message = backup_to_google_drive()
            if success:
                st.success(message)
                st.balloons()
            else:
                st.error(message)
    
    st.markdown("---")
    st.markdown("### Local CSV Backup")
    st.caption("Download a local copy of your data")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📥 Download Inventory", 
                         st.session_state.inventory.to_csv(index=False),
                         file_name=f"inventory_backup.csv")
    with col2:
        st.download_button("📥 Download Transactions",
                         st.session_state.transaction_log.to_csv(index=False),
                         file_name=f"transactions_backup.csv")

elif menu_option == "ℹ️ About":
    st.markdown("""
    # 🏬 **MAS Store** - Complete Business Management System
    
    Version: 1.0.0
    
    ## Features
    - ✅ **Purchase Management**: Record product purchases with cost tracking
    - 💰 **Sales Management**: Process sales with automatic profit calculation
    - 📊 **Real-time PNL**: Complete profit & loss analysis dashboard
    - 📝 **Expense Tracking**: Record expenses and withdrawals
    - 📜 **Transaction History**: Complete audit log of all transactions
    - ☁️ **Cloud Backup**: Sync to Google Sheets and backup to Google Drive
    - 🔒 **Data Security**: All data stored locally with optional cloud sync
    
    ## Technology Stack
    - **Frontend**: Streamlit
    - **Data Processing**: Pandas
    - **Visualization**: Plotly
    - **Cloud Integration**: Google Sheets API, Google Drive API
    - **Data Storage**: CSV files (local), Google Sheets (cloud)
    
    ## Support
    For issues or feature requests, please contact the development team.
    
    ---
    *© 2026 MAS Store. All rights reserved.*
    """)
