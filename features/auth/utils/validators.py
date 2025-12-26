import re

class Validators:
    
    @staticmethod
    def validate_password(password: str) -> str:

        """
        Validates a password string with the following rules:
        - At least 8 characters.
        - At least one uppercase letter.
        - At least one lowercase letter.
        - At least one digit.
        - At least one special character.
        
        Args:
            password: The password string to validate.

        raises: 
            ValueError if any rule is not met.

        return -> The validated password string.
        """

        # Mínimo 8 caracteres
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        # Al menos una mayúscula
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        # Al menos una minúscula
        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")
        # Al menos un número
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")
        # Al menos un símbolo especial (incluye guion explícitamente)
        special_chars = set("!@#$%^&*()_=+[]{};:,.<>?/\\|~`'\"-")
        if not any(c in special_chars for c in password):
            raise ValueError("Password must contain at least one special character")

        return password

    @staticmethod
    def validate_us_phone(Phone: str) -> str:

        """
        Validates and normalizes a US phone number to the format +1XXXXXXXXXX.

        Args:
            phone: The phone number string to validate.

        raises: 
            ValueError if the phone number is invalid.

        return -> The normalized phone number string in E.164 format.
        """

        pattern = re.compile(
            r"^(?:\+1\s?)?\(?([2-9][0-9]{2})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})$"
        )

        if not pattern.match(Phone):
            raise ValueError(
                "Invalid phone number. Examples: +1 (555) 123-4567, 555-123-4567, 5551234567"
            )

        # Normalización al formato E.164
        digits = re.sub(r"\D", "", Phone)
        if len(digits) == 10:
            digits = "1" + digits
        normalized = f"+{digits}"

        return normalized


validators = Validators()