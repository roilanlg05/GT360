
def get_support_email_template(name: str, email: str, category: str, subject: str, message: str) -> str:
    """
    Genera el HTML para el email de notificación de soporte

    Args:
        name: Nombre del cliente
        email: Email del cliente
        category: Categoría del mensaje
        subject: Asunto del mensaje
        message: Contenido del mensaje

    Returns:
        str: HTML del email
    """
    category_labels = {
        "bug": "Bug Report",
        "feature": "Feature Request",
        "question": "Question",
        "other": "Other"
    }

    category_label = category_labels.get(category, category)

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Support Request - GT 360</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }}
            .email-container {{
                max-width: 600px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 4px;
                overflow: hidden;
            }}
            .header {{
                background-color: #1a365d;
                padding: 24px;
                text-align: center;
            }}
            .header h1 {{
                color: #ffffff;
                margin: 0;
                font-size: 20px;
                font-weight: 600;
            }}
            .content {{
                padding: 32px;
                color: #333333;
                line-height: 1.6;
            }}
            .field {{
                margin-bottom: 20px;
            }}
            .field-label {{
                font-size: 12px;
                font-weight: 600;
                color: #666666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 4px;
            }}
            .field-value {{
                font-size: 15px;
                color: #333333;
            }}
            .category-badge {{
                display: inline-block;
                background-color: #e8f4f8;
                color: #1a365d;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
            }}
            .message-box {{
                background-color: #f8f8f8;
                border-left: 3px solid #1a365d;
                padding: 16px;
                margin-top: 8px;
                white-space: pre-wrap;
                font-size: 14px;
                color: #444444;
            }}
            .divider {{
                height: 1px;
                background-color: #e5e5e5;
                margin: 24px 0;
            }}
            .reply-note {{
                font-size: 13px;
                color: #888888;
                margin-top: 24px;
            }}
            .reply-note a {{
                color: #1a365d;
                text-decoration: none;
            }}
            .footer {{
                background-color: #fafafa;
                padding: 20px 32px;
                text-align: center;
                border-top: 1px solid #e5e5e5;
            }}
            .footer p {{
                margin: 0;
                font-size: 12px;
                color: #999999;
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <h1>New Support Request</h1>
            </div>

            <div class="content">
                <div class="field">
                    <div class="field-label">From</div>
                    <div class="field-value">{name}</div>
                </div>

                <div class="field">
                    <div class="field-label">Email</div>
                    <div class="field-value"><a href="mailto:{email}" style="color: #1a365d; text-decoration: none;">{email}</a></div>
                </div>

                <div class="field">
                    <div class="field-label">Category</div>
                    <div class="field-value"><span class="category-badge">{category_label}</span></div>
                </div>

                <div class="divider"></div>

                <div class="field">
                    <div class="field-label">Subject</div>
                    <div class="field-value" style="font-weight: 500;">{subject}</div>
                </div>

                <div class="field">
                    <div class="field-label">Message</div>
                    <div class="message-box">{message}</div>
                </div>

                <p class="reply-note">
                    Reply directly to this email to respond to <a href="mailto:{email}">{email}</a>
                </p>
            </div>

            <div class="footer">
                <p>GT 360 Support System</p>
            </div>
        </div>
    </body>
    </html>
    """
