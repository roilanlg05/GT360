
def get_password_reset_email_template(reset_url: str) -> str:
    """
    Genera el HTML para el email de recuperación de contraseña

    Args:
        reset_url: URL con el token para resetear la contraseña

    Returns:
        str: HTML del email
    """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reset Your Password - GT 360</title>
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
            .reset-button {{
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
            .security-note {{
                background-color: #f8f8f8;
                border-left: 3px solid #1a365d;
                padding: 12px 16px;
                margin: 24px 0;
                font-size: 13px;
                color: #666666;
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
                <p>We received a request to reset your password.</p>
                <p>Click the button below to create a new password:</p>

                <div class="button-container">
                    <a href="{reset_url}" class="reset-button">Reset Password</a>
                </div>

                <div class="security-note">
                    This link expires in 30 minutes and can only be used once.
                </div>

                <div class="divider"></div>

                <p class="alternative-link">
                    If the button doesn't work, copy and paste this link into your browser:<br>
                    <a href="{reset_url}">{reset_url}</a>
                </p>

                <p class="note">
                    If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.
                </p>
            </div>

            <div class="footer">
                <p>GT 360 - Ground Transportation Management</p>
            </div>
        </div>
    </body>
    </html>
    """
