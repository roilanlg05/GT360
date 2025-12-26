
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
        <title>Reset Your Password</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f4f4;
                margin: 0;
                padding: 0;
            }}
            .email-container {{
                max-width: 600px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 40px 20px;
                text-align: center;
            }}
            .header h1 {{
                color: #ffffff;
                margin: 0;
                font-size: 28px;
                font-weight: 600;
            }}
            .content {{
                padding: 40px 30px;
                color: #333333;
                line-height: 1.6;
            }}
            .content h2 {{
                color: #667eea;
                font-size: 24px;
                margin-top: 0;
                margin-bottom: 20px;
            }}
            .content p {{
                margin: 15px 0;
                font-size: 16px;
            }}
            .button-container {{
                text-align: center;
                margin: 35px 0;
            }}
            .reset-button {{
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #ffffff;
                text-decoration: none;
                padding: 15px 40px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 600;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                transition: transform 0.2s ease;
            }}
            .reset-button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
            }}
            .security-notice {{
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 15px;
                margin: 25px 0;
                border-radius: 4px;
            }}
            .security-notice p {{
                margin: 5px 0;
                font-size: 14px;
                color: #856404;
            }}
            .alternative-link {{
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 6px;
                margin: 25px 0;
                word-break: break-all;
            }}
            .alternative-link p {{
                margin: 5px 0;
                font-size: 13px;
                color: #6c757d;
            }}
            .alternative-link a {{
                color: #667eea;
                text-decoration: none;
                word-break: break-all;
            }}
            .footer {{
                background-color: #f8f9fa;
                padding: 30px;
                text-align: center;
                border-top: 1px solid #e9ecef;
            }}
            .footer p {{
                margin: 10px 0;
                font-size: 14px;
                color: #6c757d;
            }}
            .footer a {{
                color: #667eea;
                text-decoration: none;
            }}
            .expiration {{
                color: #dc3545;
                font-weight: 600;
            }}
            @media only screen and (max-width: 600px) {{
                .email-container {{
                    margin: 20px 10px;
                }}
                .content {{
                    padding: 30px 20px;
                }}
                .reset-button {{
                    padding: 12px 30px;
                    font-size: 14px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <!-- Header -->
            <div class="header">
                <h1>🔐 Api360</h1>
            </div>

            <!-- Content -->
            <div class="content">
                <h2>Reset Your Password</h2>
                <p>Hello,</p>
                <p>
                    We received a request to reset your password for your Api360 account. 
                    If you made this request, click the button below to create a new password:
                </p>

                <!-- Reset Button -->
                <div class="button-container">
                    <a href="{reset_url}" class="reset-button">Reset My Password</a>
                </div>

                <!-- Security Notice -->
                <div class="security-notice">
                    <p><strong>⚠️ Security Notice:</strong></p>
                    <p>
                        This link will <span class="expiration">expire in 30 minutes</span> for security reasons. 
                        After using this link once, it will become invalid.
                    </p>
                </div>

                <!-- Alternative Link -->
                <div class="alternative-link">
                    <p><strong>Button not working?</strong> Copy and paste this link into your browser:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                </div>

                <p>
                    If you didn't request a password reset, please ignore this email. 
                    Your password will remain unchanged, and your account is secure.
                </p>

                <p>
                    If you're concerned about your account's security, please contact our support team immediately.
                </p>

                <p style="margin-top: 30px;">
                    Best regards,<br>
                    <strong>The Api360 Team</strong>
                </p>
            </div>

            <!-- Footer -->
            <div class="footer">
                <p>
                    This is an automated message from Api360.<br>
                    Please do not reply to this email.
                </p>
                <p>
                    Need help? <a href="https://www.optionstriker.com/support">Contact Support</a>
                </p>
                <p style="margin-top: 20px; font-size: 12px; color: #999;">
                    © 2025 Api360. All rights reserved.<br>
                    <a href="https://www.optionstriker.com/privacy">Privacy Policy</a> | 
                    <a href="https://www.optionstriker.com/terms">Terms of Service</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """