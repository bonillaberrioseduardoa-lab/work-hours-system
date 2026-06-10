import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Work Hours System", layout="wide")

REQUIRED_HOURS = 360
SHEET_NAME = "Food Security Work Hours"
WORKSHEET_NAME = "Hoja 1"

STUDENTS = [
    "Select Student",
    "Alejandro O.",
    "Eduardo B.",
    "Alexi W.",
    "Sebastian D."
]

COLUMNS = [
    "ID",
    "Student/Worker",
    "Date",
    "Entry Time",
    "Exit Time",
    "Total Hours",
    "Work Type",
    "Remark",
    "Status",
    "Supervisor Note",
    "Submitted At"
]


def connect_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open(SHEET_NAME)
    worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    return worksheet


def load_data():
    worksheet = connect_sheet()
    records = worksheet.get_all_records()

    if not records:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(records)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
    df["Total Hours"] = pd.to_numeric(df["Total Hours"], errors="coerce").fillna(0)
    df["Status"] = df["Status"].fillna("Pending").astype(str)
    df["Supervisor Note"] = df["Supervisor Note"].fillna("").astype(str)

    return df[COLUMNS]


def save_data(df):
    worksheet = connect_sheet()
    worksheet.clear()
    worksheet.update([COLUMNS] + df[COLUMNS].astype(str).values.tolist())


def calculate_hours(entry_time, exit_time):
    entry_dt = datetime.combine(datetime.today(), entry_time)
    exit_dt = datetime.combine(datetime.today(), exit_time)

    if exit_dt < entry_dt:
        return None

    return round((exit_dt - entry_dt).total_seconds() / 3600, 2)


st.title("Work Hours Registration System")

menu = st.sidebar.radio(
    "Select Section",
    ["Register Hours", "Supervisor Panel"]
)

if menu == "Register Hours":
    st.header("Register Work Hours")

    with st.form("hours_form"):
        name = st.selectbox("Student/Worker Name", STUDENTS)
        date = st.date_input("Date")
        entry_time = st.time_input("Entry Time")
        exit_time = st.time_input("Exit Time")
        work_type = st.selectbox("Work Type", ["In Person", "Virtual"])
        remark = st.text_area("Remark: What did you work on during this time?")

        submitted = st.form_submit_button("Submit Hours")

        if submitted:
            if name == "Select Student" or not remark.strip():
                st.error("Please select your name and write a remark.")
            else:
                total_hours = calculate_hours(entry_time, exit_time)

                if total_hours is None:
                    st.error("Exit time cannot be earlier than entry time.")
                else:
                    df = load_data()
                    new_id = 1 if df.empty else int(df["ID"].max()) + 1

                    new_row = {
                        "ID": new_id,
                        "Student/Worker": name,
                        "Date": date.strftime("%Y-%m-%d"),
                        "Entry Time": entry_time.strftime("%H:%M"),
                        "Exit Time": exit_time.strftime("%H:%M"),
                        "Total Hours": total_hours,
                        "Work Type": work_type,
                        "Remark": remark.strip(),
                        "Status": "Pending",
                        "Supervisor Note": "",
                        "Submitted At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(df)

                    st.success("Hours submitted successfully.")
                    st.info(f"Total hours registered: {total_hours}")

elif menu == "Supervisor Panel":
    st.header("Supervisor Panel")

    password = st.text_input("Enter supervisor password", type="password")

    if password == st.secrets["ADMIN_PASSWORD"]:
        st.success("Access granted.")

        df = load_data()

        if df.empty:
            st.warning("No records yet.")
        else:
            st.subheader("Summary Dashboard")

            total_hours = round(df["Total Hours"].sum(), 2)
            pending_count = len(df[df["Status"] == "Pending"])
            approved_count = len(df[df["Status"] == "Approved"])
            rejected_count = len(df[df["Status"] == "Rejected"])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Hours", total_hours)
            col2.metric("Pending", pending_count)
            col3.metric("Approved", approved_count)
            col4.metric("Rejected", rejected_count)

            st.subheader("Progress by Student")

            summary = (
                df.groupby("Student/Worker")["Total Hours"]
                .sum()
                .reset_index()
                .sort_values(by="Student/Worker")
            )

            summary["Required Hours"] = REQUIRED_HOURS
            summary["Remaining Hours"] = summary["Required Hours"] - summary["Total Hours"]
            summary["Remaining Hours"] = summary["Remaining Hours"].apply(lambda x: max(x, 0))
            summary["Progress %"] = round((summary["Total Hours"] / REQUIRED_HOURS) * 100, 2)

            st.dataframe(summary, use_container_width=True)

            st.subheader("Filters")

            names = ["All"] + sorted(df["Student/Worker"].dropna().unique().tolist())
            statuses = ["All"] + sorted(df["Status"].dropna().unique().tolist())
            work_types = ["All"] + sorted(df["Work Type"].dropna().unique().tolist())

            selected_name = st.selectbox("Filter by student/worker", names)
            selected_status = st.selectbox("Filter by status", statuses)
            selected_type = st.selectbox("Filter by work type", work_types)

            filtered_df = df.copy()

            if selected_name != "All":
                filtered_df = filtered_df[filtered_df["Student/Worker"] == selected_name]

            if selected_status != "All":
                filtered_df = filtered_df[filtered_df["Status"] == selected_status]

            if selected_type != "All":
                filtered_df = filtered_df[filtered_df["Work Type"] == selected_type]

            st.subheader("Registered Records")
            st.dataframe(filtered_df, use_container_width=True)

            st.subheader("Approve / Reject / Edit Record")

            record_ids = filtered_df["ID"].dropna().astype(int).tolist()

            if record_ids:
                selected_id = st.selectbox("Select record ID", record_ids)

                selected_row = df[df["ID"] == selected_id].iloc[0]

                st.write("Selected Record:")
                st.write(selected_row)

                current_status = selected_row["Status"]
                if current_status not in ["Pending", "Approved", "Rejected"]:
                    current_status = "Pending"

                new_status = st.selectbox(
                    "Status",
                    ["Pending", "Approved", "Rejected"],
                    index=["Pending", "Approved", "Rejected"].index(current_status)
                )

                supervisor_note = st.text_area(
                    "Supervisor Note",
                    value="" if pd.isna(selected_row["Supervisor Note"]) else str(selected_row["Supervisor Note"])
                )

                col_a, col_b = st.columns(2)

                with col_a:
                    if st.button("Update Record"):
                        row_index = df.index[df["ID"] == selected_id][0]
                        df.at[row_index, "Status"] = new_status
                        df.at[row_index, "Supervisor Note"] = str(supervisor_note)
                        save_data(df)
                        st.success("Record updated successfully.")
                        st.rerun()

                with col_b:
                    if st.button("Delete Record"):
                        df = df[df["ID"] != selected_id]
                        save_data(df)
                        st.warning("Record deleted.")
                        st.rerun()

            st.subheader("Download Reports")

            st.download_button(
                label="Download Filtered Excel Report",
                data=filtered_df.to_csv(index=False).encode("utf-8"),
                file_name="work_hours_report.csv",
                mime="text/csv"
            )

            st.download_button(
                label="Download Summary by Student",
                data=summary.to_csv(index=False).encode("utf-8"),
                file_name="summary_by_student.csv",
                mime="text/csv"
            )

    elif password:
        st.error("Incorrect password.")