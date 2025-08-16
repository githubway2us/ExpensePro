import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
import time
import logging
from typing import Tuple, Optional, Dict, Any

# Configuration
API_URL = "http://localhost:5001/api"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------- STATE MANAGEMENT -------------------
def initialize_session_state():
    """Initialize session state variables."""
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user_id" not in st.session_state:
        st.session_state.user_id = None

# ------------------- HELPERS -------------------
def auth_header() -> Dict[str, str]:
    """Generate authorization header with bearer token."""
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}

def safe_request(method: str, url: str, **kwargs) -> Tuple[Optional[int], Optional[Any], str]:
    """Handle API requests with proper error handling and logging."""
    try:
        res = requests.request(method, url, timeout=10, **kwargs)
        content_type = res.headers.get('Content-Type', '')
        if content_type.startswith('application/json'):
            try:
                data = res.json()
            except ValueError:
                data = None
                logger.warning(f"Non-JSON response from {url}: {res.text}")
        elif content_type.startswith('text/csv'):
            data = res.content  # เก็บ binary content สำหรับไฟล์ CSV
        else:
            data = res.text
            logger.warning(f"Unexpected content type from {url}: {content_type}")
        return res.status_code, data, res.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {str(e)}")
        return None, None, str(e)

def validate_input(data: Dict[str, Any], required_fields: list) -> Tuple[bool, str]:
    """Validate input data for required fields."""
    for field in required_fields:
        if not data.get(field):
            return False, f"กรุณากรอก{field}"
    return True, ""

def get_date_range(period: str, year: int = None, month: int = None, week: int = None) -> Tuple[str, str]:
    """Calculate date range for weekly, monthly, or yearly analysis."""
    today = date.today()
    if period == "รายสัปดาห์":
        if year is None or week is None:
            start = today - timedelta(days=today.weekday())  # Monday of current week
            end = start + timedelta(days=6)  # Sunday
        else:
            first_day_of_year = date(year, 1, 1)
            days_to_monday = (7 - first_day_of_year.weekday()) % 7
            start = first_day_of_year + timedelta(days=days_to_monday + (week - 1) * 7)
            end = start + timedelta(days=6)
            # Ensure dates are within the year
            if end.year > year:
                end = date(year, 12, 31)
    elif period == "รายเดือน":
        if year is None or month is None:
            start = today.replace(day=1)  # First day of current month
            end = (start + timedelta(days=31)).replace(day=1) - timedelta(days=1)  # Last day of current month
        else:
            start = date(year, month, 1)
            end = (start + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    else:  # รายปี
        start = date(year or today.year, 1, 1)  # First day of selected or current year
        end = date(year or today.year, 12, 31)  # Last day of selected or current year
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

# ------------------- UI COMPONENTS -------------------
def login_ui():
    """Render login interface."""
    with st.form("login_form"):
        st.subheader("เข้าสู่ระบบ")
        username = st.text_input("ชื่อผู้ใช้")
        password = st.text_input("รหัสผ่าน", type="password")
        submit = st.form_submit_button("ล็อกอิน")

        if submit:
            is_valid, msg = validate_input({"username": username, "password": password}, 
                                        ["username", "password"])
            if not is_valid:
                st.error(msg)
                return

            status, data, text = safe_request("POST", f"{API_URL}/login", 
                                           json={"username": username, "password": password})
            if status == 200 and data.get("access_token"):
                st.session_state.token = data["access_token"]
                st.session_state.user_id = data.get("user_id")
                st.success("เข้าสู่ระบบสำเร็จ")
                st.rerun()
            else:
                st.error(data.get("msg", "ล็อกอินล้มเหลว") if data else text)

def register_ui():
    """Render registration interface."""
    with st.form("register_form"):
        st.subheader("สมัครสมาชิก")
        username = st.text_input("ชื่อผู้ใช้")
        email = st.text_input("อีเมล")
        password = st.text_input("รหัสผ่าน", type="password")
        submit = st.form_submit_button("สมัครสมาชิก")

        if submit:
            is_valid, msg = validate_input({"username": username, "email": email, "password": password},
                                        ["username", "email", "password"])
            if not is_valid:
                st.error(msg)
                return

            status, data, text = safe_request("POST", f"{API_URL}/register", 
                                           json={"username": username, "email": email, "password": password})
            if status == 201:
                st.success("สมัครสำเร็จ กรุณาเข้าสู่ระบบ")
            else:
                st.error(data.get("msg", "สมัครไม่สำเร็จ") if data else text)

def category_ui():
    """Render category management interface."""
    st.subheader("จัดการหมวดหมู่")
    
    # Fetch and display categories
    status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
    if status == 200 and cats:
        df = pd.DataFrame(cats)
        st.dataframe(df.style.format({"id": "{:d}"}))
    else:
        st.error(f"ไม่สามารถโหลดหมวดหมู่ได้: {text}")
        cats = []

    # Add new category
    with st.form("category_form"):
        name = st.text_input("ชื่อหมวดหมู่ใหม่")
        cat_type = st.selectbox("ประเภท", ["expense", "income"], index=0)
        submit = st.form_submit_button("เพิ่มหมวดหมู่")
        
        if submit:
            is_valid, msg = validate_input({"name": name}, ["name"])
            if not is_valid:
                st.error(msg)
                return
                
            status, data, text = safe_request("POST", f"{API_URL}/categories", 
                                           json={"name": name, "type": cat_type}, headers=auth_header())
            if status == 201:
                st.success("เพิ่มหมวดหมู่สำเร็จ")
                st.rerun()
            else:
                st.error(data.get("msg", "เพิ่มหมวดหมู่ล้มเหลว") if data else text)

def add_expense_ui():
    """Render expense creation interface."""
    st.subheader("เพิ่มค่าใช้จ่าย")
    
    # Check token
    if not st.session_state.token:
        st.error("ไม่พบ token การยืนยันตัวตน กรุณาเข้าสู่ระบบใหม่")
        return
    
    # Fetch categories
    status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
    if status != 200 or not cats:
        st.error(f"ไม่สามารถโหลดหมวดหมู่ได้: {text}")
        return

    expense_cats = {c["name"]: c["id"] for c in cats if isinstance(c, dict) and c.get("type") == "expense"}
    if not expense_cats:
        st.warning("ไม่มีหมวดหมู่ค่าใช้จ่าย กรุณาเพิ่มหมวดหมู่ค่าใช้จ่ายก่อน")
        return

    with st.form("expense_form"):
        cat_name = st.selectbox("หมวดหมู่", list(expense_cats.keys()))
        amount = st.number_input("จำนวนเงิน", min_value=0.0, step=0.01, format="%.2f")
        expense_date = st.date_input("วันที่", value=date.today())
        merchant = st.text_input("ร้านค้า/ผู้รับ")
        note = st.text_area("หมายเหตุ")
        submit = st.form_submit_button("บันทึก")

        if submit:
            is_valid, msg = validate_input({"category": cat_name, "amount": amount}, 
                                        ["category", "amount"])
            if not is_valid:
                st.error(msg)
                return

            payload = {
                "category_id": expense_cats[cat_name],
                "amount": amount,
                "date": str(expense_date),
                "merchant": merchant or None,
                "note": note or None
            }
            logger.info(f"Sending expense payload: {payload}")
            with st.spinner("กำลังบันทึกค่าใช้จ่าย..."):
                status, data, text = safe_request("POST", f"{API_URL}/expenses", 
                                              json=payload, headers=auth_header())
                logger.info(f"Expense API response: status={status}, data={data}, text={text}")
                if status == 201:
                    st.success("ทำการบันทึกค่าใช้จ่ายสำเร็จ")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(data.get("msg", "บันทึกค่าใช้จ่ายล้มเหลว") if data else text)

def add_income_ui():
    """Render income creation interface."""
    st.subheader("เพิ่มรายรับ")
    
    # Check token
    if not st.session_state.token:
        st.error("ไม่พบ token การยืนยันตัวตน กรุณาเข้าสู่ระบบใหม่")
        return
    
    # Fetch categories (only income type)
    status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
    if status != 200 or not cats:
        st.error(f"ไม่สามารถโหลดหมวดหมู่ได้: {text}")
        return

    income_cats = {c["name"]: c["id"] for c in cats if isinstance(c, dict) and c.get("type") == "income"}
    if not income_cats:
        st.warning("ไม่มีหมวดหมู่รายรับ กรุณาเพิ่มหมวดหมู่รายรับก่อน")
        return

    with st.form("income_form"):
        cat_name = st.selectbox("หมวดหมู่รายรับ", list(income_cats.keys()))
        amount = st.number_input("จำนวนเงิน", min_value=0.0, step=0.01, format="%.2f")
        income_date = st.date_input("วันที่", value=date.today())
        source = st.text_input("แหล่งที่มา/ผู้จ่าย")
        note = st.text_area("หมายเหตุ")
        submit = st.form_submit_button("บันทึก")

        if submit:
            is_valid, msg = validate_input({"category": cat_name, "amount": amount}, 
                                        ["category", "amount"])
            if not is_valid:
                st.error(msg)
                return

            payload = {
                "category_id": income_cats[cat_name],
                "amount": amount,
                "date": str(income_date),
                "merchant": source or None,
                "note": note or None
            }
            logger.info(f"Sending income payload: {payload}")
            with st.spinner("กำลังบันทึกรายรับ..."):
                status, data, text = safe_request("POST", f"{API_URL}/expenses", 
                                              json=payload, headers=auth_header())
                logger.info(f"Income API response: status={status}, data={data}, text={text}")
                if status == 201:
                    st.success("ทำการบันทึกรายรับสำเร็จ")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(data.get("msg", "บันทึกรายรับล้มเหลว") if data else text)

def dashboard_ui():
    """Render dashboard interface."""
    st.subheader("แดชบอร์ดสรุปค่าใช้จ่ายและรายรับ")
    
    # Check token
    if not st.session_state.token:
        st.error("ไม่พบ token การยืนยันตัวตน กรุณาเข้าสู่ระบบใหม่")
        return

    # Period selection
    period = st.selectbox("เลือกช่วงเวลา", ["รายสัปดาห์", "รายเดือน", "รายปี"], index=1, key="dashboard_period")
    
    # Initialize year and month/week selection
    today = date.today()
    current_year = today.year
    years = list(range(current_year - 5, current_year + 1))  # Last 5 years + current year
    from_date, to_date = None, None

    if period == "รายเดือน":
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("เลือกปี", years, index=years.index(current_year), key="month_year")
        with col2:
            months = [
                "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
                "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
            ]
            selected_month = st.selectbox("เลือกเดือน", months, index=today.month - 1, key="month_select")
        month_index = months.index(selected_month) + 1
        from_date, to_date = get_date_range(period, year=selected_year, month=month_index)
    elif period == "รายสัปดาห์":
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("เลือกปี", years, index=years.index(current_year), key="week_year")
        with col2:
            weeks = [f"สัปดาห์ที่ {i}" for i in range(1, 53)]  # 52 weeks in a year
            current_week = (today - date(today.year, 1, 1)).days // 7 + 1
            selected_week = st.selectbox("เลือกสัปดาห์", weeks, index=min(current_week - 1, 51), key="week_select")
        week_index = weeks.index(selected_week) + 1
        from_date, to_date = get_date_range(period, year=selected_year, week=week_index)
    else:  # รายปี
        selected_year = st.selectbox("เลือกปี", years, index=years.index(current_year), key="year_select")
        from_date, to_date = get_date_range(period, year=selected_year)

    # Display summary metrics
    st.write(f"**สรุป{period} ({from_date} ถึง {to_date})**")
    params = {"from": from_date, "to": to_date}
    status, summary, text = safe_request("GET", f"{API_URL}/summary", headers=auth_header(), params=params)
    if status == 200 and summary:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("รายรับรวม", f"{summary.get('total_income', 0):.2f} บาท")
        with col2:
            st.metric("รายจ่ายรวม", f"{summary.get('total_expense', 0):.2f} บาท")
        with col3:
            st.metric("คงเหลือ", f"{summary.get('balance', 0):.2f} บาท")
    else:
        if status == 401:
            st.error("Token หมดอายุ กรุณาเข้าสู่ระบบใหม่")
            st.session_state.token = None
            st.rerun()
        else:
            st.error(f"ไม่สามารถโหลดข้อมูลสรุปได้: {text}")
            logger.error(f"Summary API error: status={status}, response={text}")
        return

    # Category analysis for expenses
    st.write("**การวิเคราะห์รายจ่ายตามหมวดหมู่**")
    status, expense_analysis, text = safe_request(
        "GET", f"{API_URL}/analysis", 
        params={"group_by": "category_id", "only_expense": "1", "from": from_date, "to": to_date},
        headers=auth_header()
    )
    if status == 200 and expense_analysis:
        df_expense = pd.DataFrame(expense_analysis)
        if not df_expense.empty:
            status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
            cat_map = {c["id"]: c["name"] for c in cats} if status == 200 and cats else {}
            df_expense["หมวดหมู่"] = df_expense["group"].apply(lambda cid: cat_map.get(cid, "ไม่ทราบ"))
            df_expense["จำนวนเงิน"] = df_expense["total"]  # Keep as float
            st.write("**สรุปรายจ่ายตามหมวดหมู่**")
            st.dataframe(df_expense[["หมวดหมู่", "จำนวนเงิน"]].style.format({"จำนวนเงิน": "{:.2f}"}))
            fig_expense = px.pie(
                df_expense, names="หมวดหมู่", values="total", 
                title=f"สัดส่วนรายจ่าย{period}", 
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig_expense.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_expense, use_container_width=True)
        else:
            st.info("ไม่มีข้อมูลรายจ่ายสำหรับช่วงเวลานี้")
    else:
        st.error(f"ไม่สามารถโหลดข้อมูลวิเคราะห์รายจ่ายได้: {text}")

    # Category analysis for income
    st.write("**การวิเคราะห์รายรับตามหมวดหมู่**")
    status, income_analysis, text = safe_request(
        "GET", f"{API_URL}/analysis", 
        params={"group_by": "category_id", "only_expense": "0", "from": from_date, "to": to_date},
        headers=auth_header()
    )
    if status == 200 and income_analysis:
        df_income = pd.DataFrame(income_analysis)
        if not df_income.empty:
            status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
            cat_map = {c["id"]: c["name"] for c in cats} if status == 200 and cats else {}
            df_income["หมวดหมู่"] = df_income["group"].apply(lambda cid: cat_map.get(cid, "ไม่ทราบ"))
            df_income["จำนวนเงิน"] = df_income["total"]  # Keep as float
            st.write("**สรุปรายรับตามหมวดหมู่**")
            st.dataframe(df_income[["หมวดหมู่", "จำนวนเงิน"]].style.format({"จำนวนเงิน": "{:.2f}"}))
            fig_income = px.pie(
                df_income, names="หมวดหมู่", values="total", 
                title=f"สัดส่วนรายรับ{period}", 
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig_income.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_income, use_container_width=True)
        else:
            st.info("ไม่มีข้อมูลรายรับสำหรับช่วงเวลานี้")
    else:
        st.error(f"ไม่สามารถโหลดข้อมูลวิเคราะห์รายรับได้: {text}")

    # Recent transactions
    st.write("**รายการล่าสุด**")
    status, expenses, text = safe_request(
        "GET", f"{API_URL}/expenses", 
        params={"from": from_date, "to": to_date},
        headers=auth_header()
    )
    if status == 200 and expenses:
        df = pd.DataFrame(expenses)
        if not df.empty:
            status, cats, text = safe_request("GET", f"{API_URL}/categories", headers=auth_header())
            cat_map = {c["id"]: c["name"] for c in cats} if status == 200 and cats else {}
            df["หมวดหมู่"] = df["category_id"].apply(lambda cid: cat_map.get(cid, "ไม่ทราบ"))
            df["ประเภท"] = df["category_id"].apply(
                lambda cid: next((c["type"] for c in cats if c["id"] == cid), "ไม่ทราบ")
            )
            df = df[["date", "หมวดหมู่", "ประเภท", "amount", "merchant", "account", "project", "tags", "note"]]
            df.columns = ["วันที่", "หมวดหมู่", "ประเภท", "จำนวนเงิน", "แหล่งที่มา/ร้านค้า", "บัญชี", "โปรเจกต์", "แท็ก", "หมายเหตุ"]
            st.dataframe(df.style.format({"จำนวนเงิน": "{:.2f}"}))
        else:
            st.info("ไม่มีรายการในช่วงเวลานี้")
    else:
        st.error(f"ไม่สามารถโหลดรายการล่าสุดได้: {text}")

def import_export_ui():
    """Render import/export interface."""
    st.subheader("นำเข้า / ส่งออก ข้อมูล")
    
    # Check token
    if not st.session_state.token:
        st.error("ไม่พบ token การยืนยันตัวตน กรุณาเข้าสู่ระบบใหม่")
        return
    
    # Backup warning
    st.warning("**คำเตือน**: กรุณาส่งออกข้อมูลเป็น CSV เพื่อสำรองข้อมูลก่อนนำเข้าข้อมูลใหม่หรือปิดโปรแกรมทุกครั้ง เพื่อป้องกันการสูญหายของข้อมูล")
    
    # Import CSV
    with st.form("import_form"):
        uploaded = st.file_uploader("นำเข้า CSV", type=["csv"])
        submit = st.form_submit_button("นำเข้า")
        
        if submit and uploaded:
            with st.spinner("กำลังนำเข้าข้อมูล..."):
                status, data, text = safe_request("POST", f"{API_URL}/import", 
                                               files={"file": uploaded}, headers=auth_header())
                if status == 200:
                    st.success("นำเข้าข้อมูลสำเร็จ")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(data.get("msg", "นำเข้าข้อมูลล้มเหลว") if isinstance(data, dict) else text)

    # Export CSV
    st.write("**ส่งออกข้อมูลเป็น CSV**")
    period = st.selectbox("เลือกช่วงเวลา", ["ทั้งหมด", "รายสัปดาห์", "รายเดือน", "รายปี"], index=0, key="export_period")
    if st.button("สร้างไฟล์ CSV"):
        params = {}
        if period != "ทั้งหมด":
            from_date, to_date = get_date_range(period)
            params = {"from": from_date, "to": to_date}
        
        with st.spinner("กำลังสร้างไฟล์ CSV..."):
            status, data, text = safe_request("GET", f"{API_URL}/export", 
                                           headers=auth_header(), params=params)
            if status == 200 and data:
                filename = f"expenses_{date.today().strftime('%Y%m%d')}.csv"
                st.download_button(
                    label="กดเพื่อดาวน์โหลด",
                    data=data,
                    file_name=filename,
                    mime="text/csv"
                )
                st.success("สร้างไฟล์ CSV สำเร็จ")
            else:
                if status == 401:
                    st.error("Token หมดอายุ กรุณาเข้าสู่ระบบใหม่")
                    st.session_state.token = None
                    st.rerun()
                else:
                    st.error(f"ไม่สามารถส่งออก CSV ได้: {data.get('msg', text) if isinstance(data, dict) else text}")

# ------------------- MAIN -------------------
def main():
    st.set_page_config(page_title="ExpensePro", layout="wide", initial_sidebar_state="expanded")
    initialize_session_state()

    if not st.session_state.token:
        tab_login, tab_register = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        with tab_login:
            login_ui()
        with tab_register:
            register_ui()
    else:
        menu = st.sidebar.selectbox("เมนู", 
                                  ["แดชบอร์ด", "เพิ่มรายรับ", "เพิ่มค่าใช้จ่าย", "หมวดหมู่", 
                                   "นำเข้า/ส่งออก", "ออกจากระบบ"])
        
        if menu == "แดชบอร์ด":
            dashboard_ui()
        elif menu == "เพิ่มรายรับ":
            add_income_ui()
        elif menu == "เพิ่มค่าใช้จ่าย":
            add_expense_ui()
        elif menu == "หมวดหมู่":
            category_ui()
        elif menu == "นำเข้า/ส่งออก":
            import_export_ui()
        elif menu == "ออกจากระบบ":
            st.warning("**คำเตือน**: กรุณาส่งออกข้อมูลเป็น CSV เพื่อสำรองข้อมูลก่อนออกจากระบบ เพื่อป้องกันการสูญหายของข้อมูล")
            if st.button("ยืนยันการออกจากระบบ"):
                st.session_state.token = None
                st.session_state.user_id = None
                st.success("ออกจากระบบสำเร็จ")
                st.rerun()

if __name__ == "__main__":
    main()