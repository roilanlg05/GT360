
def get_confirmation_email_template(confirmation_url: str) -> str:
    """
    Genera el HTML para el email de confirmación de cuenta

    Args:
        confirmation_url: URL con el token para verificar el email

    Returns:
        str: HTML del email
    """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify Your Email - GT 360</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }}
            .email-container {{
                max-width: 520px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 4px;
                overflow: hidden;
            }}
            .header {{
                background-color: #1a365d;
                padding: 32px 24px;
                text-align: center;
            }}
            .header h1 {{
                color: #ffffff;
                margin: 0;
                font-size: 24px;
                font-weight: 600;
                letter-spacing: 1px;
            }}
            .content {{
                padding: 40px 32px;
                color: #333333;
                line-height: 1.6;
            }}
            .content p {{
                margin: 0 0 16px 0;
                font-size: 15px;
                color: #4a4a4a;
            }}
            .button-container {{
                text-align: center;
                margin: 32px 0;
            }}
            .confirm-button {{
                display: inline-block;
                background-color: #1a365d;
                color: #ffffff;
                text-decoration: none;
                padding: 14px 32px;
                border-radius: 4px;
                font-size: 15px;
                font-weight: 500;
            }}
            .divider {{
                height: 1px;
                background-color: #e5e5e5;
                margin: 24px 0;
            }}
            .alternative-link {{
                font-size: 13px;
                color: #666666;
                word-break: break-all;
            }}
            .alternative-link a {{
                color: #1a365d;
                text-decoration: none;
            }}
            .note {{
                font-size: 13px;
                color: #888888;
                margin-top: 24px;
            }}
            .footer {{
                background-color: #fafafa;
                padding: 24px 32px;
                text-align: center;
                border-top: 1px solid #e5e5e5;
            }}
            .footer p {{
                margin: 0;
                font-size: 12px;
                color: #999999;
            }}
            @media only screen and (max-width: 600px) {{
                .email-container {{
                    margin: 0;
                    border-radius: 0;
                }}
                .content {{
                    padding: 32px 24px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <h1>GT 360</h1>
            </div>

            <div class="content">
                <p>Welcome to GT 360.</p>
                <p>Please verify your email address to complete your account setup.</p>

                <div class="button-container">
                    <a href="{confirmation_url}" class="confirm-button">Verify Email</a>
                </div>

                <div class="divider"></div>

                <p class="alternative-link">
                    If the button doesn't work, copy and paste this link into your browser:<br>
                    <a href="{confirmation_url}">{confirmation_url}</a>
                </p>

                <p class="note">
                    This link expires in 24 hours. If you didn't create an account, you can ignore this email.
                </p>
            </div>

            <div class="footer">
                <p>GT 360 - Ground Transportation Management</p>
            </div>
        </div>
    </body>
    </html>
    """
