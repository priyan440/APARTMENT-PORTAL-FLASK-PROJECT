import io
import base64
import json
import qrcode
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_qr_code_base64(data_payload: dict) -> str:
    """Generates a QR code from data payload and returns base64 string data URI."""
    qr_str = json.dumps(data_payload, separators=(',', ':'))
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def generate_booking_pdf(booking: dict) -> bytes:
    """Generates a downloadable PDF receipt for an approved amenity booking using ReportLab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReceiptTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=1, # Center
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        "ReceiptSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
        spaceAfter=15
    )
    bold_style = ParagraphStyle(
        "BoldText",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e293b")
    )
    normal_style = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#334155")
    )

    elements = []
    
    # Header
    elements.append(Paragraph("GREENWOOD ESTATES RESIDENTIAL PORTAL", title_style))
    elements.append(Paragraph("OFFICIAL AMENITY BOOKING CONFIRMATION & RECEIPT", subtitle_style))
    elements.append(Spacer(1, 10))

    # Meta banner table
    banner_data = [
        [
            Paragraph(f"<b>Receipt No:</b> {booking.get('receipt_number', 'N/A')}", normal_style),
            Paragraph(f"<b>Booking ID:</b> {booking.get('booking_id', 'N/A')}", normal_style)
        ],
        [
            Paragraph(f"<b>Status:</b> <font color='#16a34a'><b>{booking.get('status', 'APPROVED')}</b></font>", normal_style),
            Paragraph(f"<b>Issued Date:</b> {booking.get('approval', {}).get('approved_at', 'Today')[:10] if isinstance(booking.get('approval', {}).get('approved_at'), str) else 'Today'}", normal_style)
        ]
    ]
    banner_table = Table(banner_data, colWidths=[260, 260])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(banner_table)
    elements.append(Spacer(1, 15))

    # Details table
    approval_info = booking.get("approval", {})
    details_data = [
        [Paragraph("Resident Name", bold_style), Paragraph(str(booking.get("resident_name", "")), normal_style)],
        [Paragraph("Block & Flat", bold_style), Paragraph(f"Block {booking.get('block', '')} - Flat {booking.get('flat', '')}", normal_style)],
        [Paragraph("Amenity Reserved", bold_style), Paragraph(f"<b>{booking.get('amenity_name', '')}</b>", normal_style)],
        [Paragraph("Reservation Date", bold_style), Paragraph(str(booking.get("booking_date", "")), normal_style)],
        [Paragraph("Slot Timing", bold_style), Paragraph(f"{booking.get('start_time', '')} to {booking.get('end_time', '')}", normal_style)],
        [Paragraph("Event Purpose", bold_style), Paragraph(str(booking.get("purpose", "General Use")), normal_style)],
        [Paragraph("Expected Attendees", bold_style), Paragraph(str(booking.get("guests_count", "N/A")), normal_style)],
        [Paragraph("Approved By", bold_style), Paragraph(f"{approval_info.get('approved_by_name', approval_info.get('approved_by', 'Manager'))}", normal_style)],
        [Paragraph("Verification Code", bold_style), Paragraph(f"VERIFIED-SEC-{booking.get('booking_id')}", normal_style)]
    ]

    details_table = Table(details_data, colWidths=[180, 340])
    details_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 15))

    # QR Code generation for PDF
    qr_payload = {
        "booking_id": booking.get("booking_id"),
        "amenity": booking.get("amenity_name"),
        "date": booking.get("booking_date"),
        "time": f"{booking.get('start_time')}-{booking.get('end_time')}",
        "status": booking.get("status")
    }
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(json.dumps(qr_payload))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0f172a", back_color="white")
    
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    
    qr_reportlab = RLImage(qr_buf, width=1.4*inch, height=1.4*inch)
    
    qr_table = Table([[
        qr_reportlab,
        Paragraph("<b>Scan at Facility Entrance</b><br/><font color='#64748b' size='8'>This encrypted QR code confirms official management authorization. Present this digital or printed pass to estate security upon arrival.</font>", normal_style)
    ]], colWidths=[110, 410])
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fafafa"))
    ]))
    elements.append(qr_table)
    elements.append(Spacer(1, 15))
    center_note_style = ParagraphStyle(
        "CenterNote",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#94a3b8"),
        alignment=1
    )
    elements.append(Paragraph("This is a computer-generated document issued by the Greenwood Estates Residential Management System. No physical signature required.", center_note_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def generate_payment_pdf(bill: dict, payment: dict) -> bytes:
    """Generates a downloadable PDF receipt for a completed maintenance bill payment."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("PayTitle", parent=styles["Heading1"], fontSize=18, alignment=1, spaceAfter=4)
    subtitle_style = ParagraphStyle("PaySubtitle", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), alignment=1, spaceAfter=15)
    bold_style = ParagraphStyle("PayBold", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold")
    normal_style = ParagraphStyle("PayNormal", parent=styles["Normal"], fontSize=10)
    pay_note_style = ParagraphStyle("PayNote", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"), alignment=1)

    elements = [
        Paragraph("GREENWOOD ESTATES RESIDENTIAL PORTAL", title_style),
        Paragraph("MAINTENANCE PAYMENT ACKNOWLEDGEMENT RECEIPT", subtitle_style),
        Spacer(1, 10)
    ]

    meta_data = [
        [Paragraph(f"<b>Payment ID:</b> {payment.get('payment_id')}", normal_style), Paragraph(f"<b>Bill ID:</b> {bill.get('bill_id')}", normal_style)],
        [Paragraph(f"<b>Transaction Ref:</b> {payment.get('transaction_ref')}", normal_style), Paragraph(f"<b>Date:</b> {payment.get('payment_date')[:10] if isinstance(payment.get('payment_date'), str) else 'Today'}", normal_style)],
        [Paragraph(f"<b>Resident:</b> {bill.get('resident_name')}", normal_style), Paragraph(f"<b>Flat:</b> Block {bill.get('block')} - {bill.get('flat')}", normal_style)]
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    comps = bill.get("components", {})
    breakdown_data = [
        [Paragraph("<b>Charge Component</b>", bold_style), Paragraph("<b>Amount (INR)</b>", bold_style)],
        [Paragraph("Monthly Maintenance Charge", normal_style), Paragraph(f"₹{comps.get('maintenance_charge', 0):,}", normal_style)],
        [Paragraph("Water Supply Charges", normal_style), Paragraph(f"₹{comps.get('water_charge', 0):,}", normal_style)],
        [Paragraph("Designated Parking Slot Fee", normal_style), Paragraph(f"₹{comps.get('parking_charge', 0):,}", normal_style)],
        [Paragraph("Other Amenities & Common Services", normal_style), Paragraph(f"₹{comps.get('other_charge', 0):,}", normal_style)],
        [Paragraph("Late Surcharge Fee", normal_style), Paragraph(f"₹{comps.get('late_fee', 0):,}", normal_style)],
        [Paragraph("<b>TOTAL AMOUNT PAID</b>", bold_style), Paragraph(f"<b>₹{payment.get('amount', bill.get('total_amount', 0)):,}</b>", bold_style)]
    ]
    table = Table(breakdown_data, colWidths=[360, 160])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#dcfce7")),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Status: <b>PAYMENT CONFIRMED (SUCCESS)</b>. Thank you for your timely contribution.", pay_note_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def generate_community_payment_pdf(collection: dict, payment: dict) -> bytes:
    """Generates a downloadable PDF receipt for a community collection / special contribution."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("ColPayTitle", parent=styles["Heading1"], fontSize=18, alignment=1, spaceAfter=4)
    subtitle_style = ParagraphStyle("ColPaySubtitle", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), alignment=1, spaceAfter=15)
    bold_style = ParagraphStyle("ColPayBold", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold")
    normal_style = ParagraphStyle("ColPayNormal", parent=styles["Normal"], fontSize=10)
    pay_note_style = ParagraphStyle("ColPayNote", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"), alignment=1)

    elements = [
        Paragraph("GREENWOOD ESTATES RESIDENTIAL PORTAL", title_style),
        Paragraph("COMMUNITY COLLECTION & SPECIAL CONTRIBUTION RECEIPT", subtitle_style),
        Spacer(1, 10)
    ]

    p_info = payment.get("payment", {}) or {}
    receipt_no = p_info.get("receipt_no") or f"CPR-{payment.get('payment_id', 'N/A')}"
    txn_ref = p_info.get("transaction_id") or payment.get("transaction_ref", "N/A")
    paid_date = p_info.get("paid_at", "Today")[:10] if isinstance(p_info.get("paid_at"), str) else "Today"

    meta_data = [
        [
            Paragraph(f"<b>Receipt No:</b> {receipt_no}", normal_style),
            Paragraph(f"<b>Payment ID:</b> {payment.get('payment_id')}", normal_style)
        ],
        [
            Paragraph(f"<b>Transaction Ref:</b> {txn_ref}", normal_style),
            Paragraph(f"<b>Date:</b> {paid_date}", normal_style)
        ],
        [
            Paragraph(f"<b>Resident:</b> {payment.get('resident_name')}", normal_style),
            Paragraph(f"<b>Flat:</b> Block {payment.get('block')} - {payment.get('flat')}", normal_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # Event details banner
    event_banner = [
        [
            Paragraph(f"<b>Event / Purpose:</b> {collection.get('title', payment.get('collection_title', 'Community Event'))}", bold_style),
            Paragraph(f"<b>Category:</b> {collection.get('type', payment.get('collection_type', 'Contribution'))}", normal_style)
        ],
        [
            Paragraph(f"<b>Event Date:</b> {collection.get('event_date', 'N/A')}", normal_style),
            Paragraph(f"<b>Payment Method:</b> {p_info.get('method', 'ONLINE')}", normal_style)
        ]
    ]
    event_table = Table(event_banner, colWidths=[260, 260])
    event_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#bfdbfe")),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(event_table)
    elements.append(Spacer(1, 14))

    # Participants breakdown if applicable
    participants = payment.get("participants", [])
    total_amount = float(payment.get("total_amount", payment.get("amount", 0)))
    
    breakdown_data = [
        [Paragraph("<b>Participant / Description</b>", bold_style), Paragraph("<b>Category</b>", bold_style), Paragraph("<b>Amount (INR)</b>", bold_style)]
    ]
    if participants:
        for p in participants:
            breakdown_data.append([
                Paragraph(f"{p.get('name', 'Participant')} ({p.get('relationship', 'Member')})", normal_style),
                Paragraph(str(p.get("category", "STANDARD")), normal_style),
                Paragraph(f"₹{float(p.get('amount', 0)):,.2f}", normal_style)
            ])
    else:
        breakdown_data.append([
            Paragraph(f"Special Contribution - {collection.get('title', 'Event')}", normal_style),
            Paragraph("FLAT CONTRIBUTION", normal_style),
            Paragraph(f"₹{total_amount:,.2f}", normal_style)
        ])

    breakdown_data.append([
        Paragraph("<b>TOTAL CONTRIBUTION SETTLED</b>", bold_style),
        Paragraph(f"<b>{payment.get('participant_count', len(participants) or 1)} Member(s)</b>", bold_style),
        Paragraph(f"<b>₹{total_amount:,.2f}</b>", bold_style)
    ])

    table = Table(breakdown_data, colWidths=[260, 130, 130])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#dcfce7")),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 15))

    # QR Code
    qr_payload = {
        "receipt_no": receipt_no,
        "payment_id": payment.get("payment_id"),
        "collection_id": payment.get("collection_id"),
        "amount": total_amount,
        "resident": payment.get("resident_name"),
        "flat": f"Block {payment.get('block')}-{payment.get('flat')}",
        "status": "PAID"
    }
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(json.dumps(qr_payload))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0f172a", back_color="white")
    
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_reportlab = RLImage(qr_buf, width=1.3*inch, height=1.3*inch)

    qr_table = Table([[
        qr_reportlab,
        Paragraph("<b>Official Digital Payment Verification</b><br/><font color='#64748b' size='8'>This verified QR code certifies receipt of community funds for the designated event/festival. It can be presented at event check-in desk.</font>", normal_style)
    ]], colWidths=[100, 420])
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fafafa"))
    ]))
    elements.append(qr_table)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Status: <b>PAYMENT CONFIRMED (PAID)</b>. Greenwood Estates Management Committee.", pay_note_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

