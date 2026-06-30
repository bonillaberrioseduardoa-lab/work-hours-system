import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Work Hours System", layout="wide")

REQUIRED_HOURS = 330
SHEET_NAME = "Food Security Work Hours"
WORKSHEET_NAME = "Hoja 1"
BACKUP_SHEET_NAME = "Backup"
AUDIT_SHEET_NAME = "Audit Log"

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

AUDIT_COLUMNS = [
    "Timestamp",
    "Action",
    "Student/Worker",
    "Record ID",
    "Details"
]


def connect_spreadsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )

    client = gspread.authorize(credentials)
    return client.open(SHEET_NAME)


def get_worksheet(sheet_name, headers):
    spreadsheet = connect_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=len(headers)
        )
        worksheet.append_row(headers)

    existing_headers = worksheet.row_values(1)

    if not existing_headers:
        worksheet.append_row(headers)

    return worksheet


def main_sheet():
    return get_worksheet(WORKSHEET_NAME, COLUMNS)


def backup_sheet():
    return get_worksheet(BACKUP_SHEET_NAME, COLUMNS)


def audit_sheet():
    return get_worksheet(AUDIT_SHEET_NAME, AUDIT_COLUMNS)


def log_action(action, student, record_id, details):
    try:
        audit_sheet().append_row(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                action,
                student,
                record_id,
                details
            ],
            value_input_option="USER_ENTERED"
        )
    except Exception:
        pass


def load_data():
    worksheet = main_sheet()
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


def append_record(row_dict):
    row = [row_dict.get(col, "") for col in COLUMNS]

    main_sheet().append_row(row, value_input_option="USER_ENTERED")
    backup_sheet().append_row(row, value_input_option="USER_ENTERED")

    log_action(
        action="SUBMIT",
        student=row_dict.get("Student/Worker", ""),
        record_id=row_dict.get("ID", ""),
        details="New work-hours record submitted and backed up."
    )


def update_record_in_sheet(record_id, new_status, supervisor_note):
    worksheet = main_sheet()
    all_values = worksheet.get_all_values()

    if not all_values:
        return False

    headers = all_values[0]

    try:
        id_col = headers.index("ID") + 1
        status_col = headers.index("Status") + 1
        note_col = headers.index("Supervisor Note") + 1
        student_col = headers.index("Student/Worker") + 1
    except ValueError:
        return False

    for row_number, row in enumerate(all_values[1:], start=2):
        if len(row) >= id_col and str(row[id_col - 1]) == str(record_id):
            student_name = row[student_col - 1] if len(row) >= student_col else ""

            worksheet.update_cell(row_number, status_col, new_status)
            worksheet.update_cell(row_number, note_col, supervisor_note)

            log_action(
                action="UPDATE_RECORD",
                student=student_name,
                record_id=record_id,
                details=f"Status changed to {new_status}. Supervisor note updated."
            )
            return True

    return False


def void_record_in_sheet(record_id):
    worksheet = main_sheet()
    all_values = worksheet.get_all_values()

    if not all_values:
        return False

    headers = all_values[0]

    try:
        id_col = headers.index("ID") + 1
        status_col = headers.index("Status") + 1
        note_col = headers.index("Supervisor Note") + 1
        student_col = headers.index("Student/Worker") + 1
    except ValueError:
        return False

    for row_number, row in enumerate(all_values[1:], start=2):
        if len(row) >= id_col and str(row[id_col - 1]) == str(record_id):
            student_name = row[student_col - 1] if len(row) >= student_col else ""
            existing_note = row[note_col - 1] if len(row) >= note_col else ""

            new_note = (
                f"{existing_note} | Voided by supervisor on "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ).strip(" |")

            worksheet.update_cell(row_number, status_col, "Voided")
            worksheet.update_cell(row_number, note_col, new_note)

            log_action(
                action="VOID_RECORD",
                student=student_name,
                record_id=record_id,
                details="Record was marked as Voided instead of deleted."
            )
            return True

    return False


def calculate_hours(entry_time, exit_time):
    entry_dt = datetime.combine(datetime.today(), entry_time)
    exit_dt = datetime.combine(datetime.today(), exit_time)

    if exit_dt < entry_dt:
        return None

    return round((exit_dt - entry_dt).total_seconds() / 3600, 2)


def load_audit_data():
    records = audit_sheet().get_all_records()

    if not records:
        return pd.DataFrame(columns=AUDIT_COLUMNS)

    df = pd.DataFrame(records)

    for col in AUDIT_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df[AUDIT_COLUMNS]


st.title("Work Hours Registration System")

menu = st.sidebar.radio(
    "Select Section",
    ["Register Hours", "Student Panel", "Supervisor Panel", "Admin Panel"]
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

                    append_record(new_row)

                    st.success("Hours submitted successfully.")
                    st.info(f"Total hours registered: {total_hours}")

elif menu == "Student Panel":
    st.header("Student Work Hours Panel")

    student_name = st.selectbox("Select your name", STUDENTS)
    student_password = st.text_input("Enter your password", type="password")

    if student_name != "Select Student" and student_password:
        correct_password = st.secrets["student_passwords"].get(student_name, "")

        if student_password == correct_password:
            st.success(f"Welcome, {student_name}.")

            log_action(
                action="LOGIN_STUDENT",
                student=student_name,
                record_id="",
                details="Student accessed Student Panel."
            )

            df = load_data()
            student_df = df[df["Student/Worker"] == student_name].copy()

            if student_df.empty:
                st.warning("You do not have submitted records yet.")
            else:
                approved_df = student_df[student_df["Status"] == "Approved"]
                pending_df = student_df[student_df["Status"] == "Pending"]
                rejected_df = student_df[student_df["Status"] == "Rejected"]
                voided_df = student_df[student_df["Status"] == "Voided"]

                approved_hours = round(approved_df["Total Hours"].sum(), 2)
                pending_hours = round(pending_df["Total Hours"].sum(), 2)
                rejected_hours = round(rejected_df["Total Hours"].sum(), 2)
                voided_hours = round(voided_df["Total Hours"].sum(), 2)

                remaining_hours = max(REQUIRED_HOURS - approved_hours, 0)
                progress = round((approved_hours / REQUIRED_HOURS) * 100, 2)

                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Approved Hours", approved_hours)
                col2.metric("Pending Hours", pending_hours)
                col3.metric("Rejected Hours", rejected_hours)
                col4.metric("Voided Hours", voided_hours)
                col5.metric("Remaining Hours", remaining_hours)

                st.metric("Progress", f"{progress}%")
                st.progress(min(progress / 100, 1.0))

                st.subheader("Your Submitted Records")

                st.dataframe(
                    student_df[
                        [
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
                    ],
                    use_container_width=True
                )

                st.download_button(
                    label="Download My Records",
                    data=student_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{student_name.replace(' ', '_')}_work_hours.csv",
                    mime="text/csv"
                )
        else:
            log_action(
                action="FAILED_LOGIN_STUDENT",
                student=student_name,
                record_id="",
                details="Incorrect student password attempt."
            )
            st.error("Incorrect password.")

elif menu == "Supervisor Panel":
    st.header("Supervisor Panel")

    password = st.text_input("Enter supervisor password", type="password")

    if password == st.secrets["ADMIN_PASSWORD"]:
        st.success("Access granted.")

        log_action(
            action="LOGIN_SUPERVISOR",
            student="Supervisor",
            record_id="",
            details="Supervisor accessed Supervisor Panel."
        )

        df = load_data()

        if df.empty:
            st.warning("No records yet.")
        else:
            st.subheader("Summary Dashboard")

            total_hours = round(df[df["Status"] != "Voided"]["Total Hours"].sum(), 2)
            pending_count = len(df[df["Status"] == "Pending"])
            approved_count = len(df[df["Status"] == "Approved"])
            rejected_count = len(df[df["Status"] == "Rejected"])
            voided_count = len(df[df["Status"] == "Voided"])

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Hours", total_hours)
            col2.metric("Pending", pending_count)
            col3.metric("Approved", approved_count)
            col4.metric("Rejected", rejected_count)
            col5.metric("Voided", voided_count)

            st.subheader("Progress by Student")

            active_df = df[df["Status"] != "Voided"].copy()

            summary = (
                active_df.groupby("Student/Worker")["Total Hours"]
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

                status_options = ["Pending", "Approved", "Rejected", "Voided"]

                current_status = selected_row["Status"]
                if current_status not in status_options:
                    current_status = "Pending"

                new_status = st.selectbox(
                    "Status",
                    status_options,
                    index=status_options.index(current_status)
                )

                supervisor_note = st.text_area(
                    "Supervisor Note",
                    value="" if pd.isna(selected_row["Supervisor Note"]) else str(selected_row["Supervisor Note"])
                )

                col_a, col_b = st.columns(2)

                with col_a:
                    if st.button("Update Record"):
                        success = update_record_in_sheet(
                            selected_id,
                            new_status,
                            supervisor_note
                        )

                        if success:
                            st.success("Record updated successfully.")
                            st.rerun()
                        else:
                            st.error("Could not update record.")

                with col_b:
                    if st.button("Void Record Instead of Delete"):
                        success = void_record_in_sheet(selected_id)

                        if success:
                            st.warning("Record marked as Voided. It was not deleted.")
                            st.rerun()
                        else:
                            st.error("Could not void record.")

            st.subheader("Download Reports")

            st.download_button(
                label="Download Filtered CSV Report",
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
        log_action(
            action="FAILED_LOGIN_SUPERVISOR",
            student="Supervisor",
            record_id="",
            details="Incorrect supervisor password attempt."
        )
        st.error("Incorrect password.")

elif menu == "Admin Panel":
    st.header("Admin Audit Panel")

    admin_password = st.text_input("Enter admin password", type="password")

    if admin_password == st.secrets["ADMIN_PASSWORD"]:
        st.success("Admin access granted.")

        log_action(
            action="LOGIN_ADMIN",
            student="Admin",
            record_id="",
            details="Admin accessed Audit Panel."
        )

        audit_df = load_audit_data()

        if audit_df.empty:
            st.warning("No audit records yet.")
        else:
            st.subheader("Audit Summary")

            total_events = len(audit_df)
            failed_logins = len(audit_df[audit_df["Action"].astype(str).str.contains("FAILED", na=False)])
            student_logins = len(audit_df[audit_df["Action"] == "LOGIN_STUDENT"])
            supervisor_logins = len(audit_df[audit_df["Action"] == "LOGIN_SUPERVISOR"])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Events", total_events)
            col2.metric("Failed Logins", failed_logins)
            col3.metric("Student Logins", student_logins)
            col4.metric("Supervisor Logins", supervisor_logins)

            st.subheader("Filters")

            action_options = ["All"] + sorted(audit_df["Action"].dropna().unique().tolist())
            selected_action = st.selectbox("Filter by action", action_options)

            user_options = ["All"] + sorted(audit_df["Student/Worker"].dropna().unique().tolist())
            selected_user = st.selectbox("Filter by user", user_options)

            filtered_audit = audit_df.copy()

            if selected_action != "All":
                filtered_audit = filtered_audit[filtered_audit["Action"] == selected_action]

            if selected_user != "All":
                filtered_audit = filtered_audit[filtered_audit["Student/Worker"] == selected_user]

            st.subheader("Audit Log")
            st.dataframe(filtered_audit, use_container_width=True)

            st.download_button(
                label="Download Audit Log",
                data=filtered_audit.to_csv(index=False).encode("utf-8"),
                file_name="audit_log.csv",
                mime="text/csv"
            )

    elif admin_password:
        log_action(
            action="FAILED_LOGIN_ADMIN",
            student="Admin",
            record_id="",
            details="Incorrect admin password attempt."
        )
        st.error("Incorrect admin password.")