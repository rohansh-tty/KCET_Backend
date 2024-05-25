import traceback

import frappe
import frappe.oauth
from frappe import _
from frappe.auth import LoginManager
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, get_url, logger, random_string
from frappe.utils.password import (
    check_password,
    get_password_reset_limit,
    passlibctx,
    update_password,
)
from itsdangerous import URLSafeTimedSerializer  # type: ignore


@frappe.whitelist(allow_guest=True)
def get_token(
    usr: str = None,
    pwd: str = None,
    expires_in=259200,
    expire_on=None,
    device=None,
    new_user=False,
):
    """
    Get the JWT Token
    :param user: The user in ctx
    :param password: Pwd to auth
    :param expires_in: number of seconds till expiry
    :param expire_on: yyyy-mm-dd HH:mm:ss to specify the expiry (deprecated)
    :param device: The device in ctx
    """
    user = usr
    password = pwd
    frappe.logger(__name__).debug(f"{usr} logging in")

    if not frappe.db.exists("User", user):
        frappe.logger(__name__).warning(f"Invalid User {usr} trying to log-in")
        raise frappe.ValidationError(_("Invalid User"))

    login = LoginManager()
    # login.check_if_enabled(user)
    # if not check_password(user, password):
    #    login.fail("Incorrect password", user=user)
    try:
        if new_user:
            update_password(
                user, password
            )  # update Auth Table with password for corresponding email
            frappe.logger(__name__).debug("Updating Auth Table with Password")
        else:
            frappe.logger(__name__).debug(f"Checking user password, user: {user}")
            check_password(user, password)
    except frappe.AuthenticationError as e:
        frappe.logger(__name__).debug("Invalid user or passowrd")
        frappe.throw("Invalid User or Password", frappe.AuthenticationError)
    frappe.logger(__name__).debug("User password verified")
    login.login_as(user)
    login.resume = False
    login.run_trigger("on_session_creation")

    _expires_in = expires_in
    if cint(expires_in):
        _expires_in = cint(expires_in)
    elif expire_on:
        _expires_in = (get_datetime(expire_on) - get_datetime()).total_seconds()

    token = get_bearer_token(user=user, expires_in=_expires_in)
    frappe.logger(__name__).debug("Generated bearer token...")
    if user.lower() != "administrator":
        user_details = frappe.db.get_value(
            "User",
            {
                "email": user,
            },
            as_dict=1,
        )
        frappe.logger(__name__).debug(f"user details is {user_details}")
        if user_details is not None:
            pass
            # frappe.local.response["profile_pic"] = user_details["profile_pic"]
            # frappe.local.response["user_id"] = user_details["name"]
            # frappe.local.response["organization"] = user_details["organization"]
            # org_doc = frappe.get_doc("Organization", user_details["organization"])
            # try reading it from Billing Doctype
            # frappe.local.response["pricing_plan"] = (
            #     org_doc.pricing_plan if org_doc.pricing_plan else None
            # )
            # frappe.local.response["organization_type"] = (
            #     org_doc.organization_type if org_doc.organization_type else ""
            # )

    frappe.local.response["token"] = token["access_token"]

    frappe.local.response.update(token)


def get_oauth_client():
    client = frappe.db.get_value("OAuth Client", {})

    if not client:
        # make a client
        client = frappe.get_doc(
            frappe._dict(
                doctype="OAuth Client",
                app_name="default",
                scopes="all openid",
                redirect_urls=get_url(),
                default_redirect_uri=get_url(),
                grant_type="Implicit",
                response_type="Token",
            )
        )
        client.insert(ignore_permissions=True)

    else:
        client = frappe.get_doc("OAuth Client", client)

    return client


def get_bearer_token(user, expires_in=3600):
    import hashlib

    import frappe.auth
    import jwt
    from oauthlib.oauth2.rfc6749.tokens import OAuth2Token, random_token_generator

    client = get_oauth_client()

    token = frappe._dict(
        {
            "access_token": random_token_generator(None),
            "expires_in": expires_in,
            "token_type": "Bearer",
            "scopes": client.scopes,
            "refresh_token": random_token_generator(None),
        }
    )
    bearer_token = frappe.new_doc("OAuth Bearer Token")
    bearer_token.client = client.name
    bearer_token.scopes = token["scopes"]
    bearer_token.access_token = token["access_token"]
    bearer_token.refresh_token = token["refresh_token"]
    bearer_token.expires_in = token["expires_in"] or 3600
    bearer_token.user = user
    bearer_token.save(ignore_permissions=True)
    frappe.db.commit()

    # ID Token
    id_token_header = {"typ": "jwt", "alg": "HS256"}
    id_token = {
        "aud": "token_client",
        "exp": int(
            (
                frappe.db.get_value(
                    "OAuth Bearer Token", token.access_token, "expiration_time"
                )
                - frappe.utils.datetime.datetime(1970, 1, 1)
            ).total_seconds()
        ),
        "sub": frappe.db.get_value(
            "User Social Login",
            {"parent": bearer_token.user, "provider": "frappe"},
            "userid",
        ),
        "iss": "frappe_server_url",
        "at_hash": frappe.oauth.calculate_at_hash(token.access_token, hashlib.sha256),
    }
    id_token_encoded = jwt.encode(
        id_token, "client_secret", algorithm="HS256", headers=id_token_header
    )
    id_token_encoded = frappe.safe_decode(id_token_encoded)
    token.id_token = id_token_encoded
    frappe.flags.jwt = id_token_encoded

    return token


@frappe.whitelist(methods=["POST"], allow_guest=True)
# @rate_limit(
#     key="email", limit=get_password_reset_limit, seconds=24 * 60 * 60, methods=["POST"]
# )
def custom_signup_user(name: str = None, email: str = None, password: str = None):
    try:
        user_exists = frappe.db.exists("User", {"email": email})
        print("query args >>>", frappe.request.args)
        print("user exists >>", user_exists)
        print("name, email, pass", name, email, password)
        if user_exists:
            frappe.throw(f"User with the email {email} already exists, try logging in!")
            return {"type": "failed", "message": f"User with {email} already exists"}
        # generate verification token and send email
        account_verification_token = generate_email_verification_token(
            name, email, password
        )
        site_config = frappe.get_site_config()
        verification_link = (
            site_config["frontend_baseurl"]
            + "/verify?token="
            + account_verification_token
            + "&invite="
            + str(0)
            # invite param, to switch between signup and invite
        )
        email_template = frappe.render_template(
            "cutoff_app/templates/emails/email_verify.html",
            {
                "name": name,
                "link": verification_link,
                # "task": self,
                # "task_link": f"{frontend_baseurl}/project/{construction_project.name}/task-manager-v2/task/{self.name}",
                # "assigned_to": frappe.utils.comma_and(sent_emails_to_names),
            },
        )
        frappe.sendmail(
            recipients=[email],
            sender="cutoffkcet@gmail.com",
            reference_doctype="User",
            reference_name=name,
            subject="Account Verification",
            message=email_template,
            now=True,
        )
        return {"type": "success", "message": "Signup successful"}
    except Exception as e:
        frappe.logger(__name__).error(f"User Signup failed, {traceback.print_exc(e)})")
        frappe.throw("User Signup failed, ", traceback.print_exc(e))


# Signup Email Verification Handler
def generate_email_verification_token(name, email, password):
    try:
        secret_key = frappe.get_site_config().get("secret_key")
        salt_value = frappe.get_site_config().get("security_salt")
        if secret_key is None and salt_value is None:
            frappe.logger(__name__).error("Secret Key & Salt not found in Site Config")
            frappe.throw("Secret Key & Salt not found in Site Config")
        serializer = URLSafeTimedSerializer(secret_key)
        # using email, password & org in signature, to deserialize while creating employee(which happens post email verification)
        # TODO: Password should not have any symbols, only alphanumeric OR Change this logic/delimiter
        signature = name + ":" + email + ":" + password
        return serializer.dumps(signature, salt=salt_value)
    except Exception as e:
        frappe.logger(__name__).error(f"Email Token Generation failed, {e}")
        frappe.throw(f"Email Token Generation failed, {e}")


def confirm_email_verification_token(token, expiration=600, verification_type="signup"):
    from itsdangerous.exc import BadTimeSignature  # type: ignore

    secret_key = frappe.get_site_config().get("secret_key")
    salt_value = frappe.get_site_config().get("security_salt")
    if secret_key is None and salt_value is None:
        frappe.logger(__name__).error("Secret Key & Salt not found in Site Config")
        frappe.throw("Secret Key & Salt not found in Site Config")
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        if verification_type == "signup":
            signature = serializer.loads(token, salt=salt_value, max_age=expiration)
            name, email, password = signature.split(":")
            # INFO: itsdangerous handles token expiry, returns SignatureExpired Error
            return {"name": name, "email": email, "password": password}
        elif verification_type == "invite":
            signature = serializer.loads(token, salt=salt_value, max_age=expiration)
            name, email, password = signature.split(":")
            # INFO: itsdangerous handles token expiry, returns SignatureExpired Error
            return {
                "name": name,
                "email": email,
                "password": password,
            }

        # TODO: Add a page to generate verification token, if failed the first time
    except BadTimeSignature as e:
        frappe.logger(__name__).error(
            f"Failed to confirm verification token, payload: {e.payload}, date_signed: {e.date_signed}"
        )
        frappe.throw("Failed to confirm verification token, BadTimeSignature")

    except Exception as e:
        frappe.logger(__name__).error(
            f"Failed to confirm verification token, {type(e).__name__}"
        )
        frappe.throw(f"Failed to confirm verification token, {type(e).__name__}")


@frappe.whitelist(methods=["POST"], allow_guest=True)
@rate_limit(
    key="token", limit=get_password_reset_limit, seconds=24 * 60 * 60, methods=["POST"]
)
def email_verification_handler(token):
    try:
        user_info = confirm_email_verification_token(token)
        (
            name,
            email,
            password,
        ) = (
            user_info["name"],
            user_info["email"],
            user_info["password"],
        )

        frappe.logger(__name__).debug(f"email:{email}, password:{password}")
        post_email_verification(name, email, password)
        # Get the employee doc and give him/her a role and enable his/her employee account
        # user_doc = frappe.get_doc(
        #     {"doctype": "Employee", "email": user_info["email"]}
        # )
        # user_doc.db_set("account_enabled", 1)

        return {
            "status": "success"
        }  # TODO: Have a standard response format for all observance whitelisted methods
    except Exception as e:
        frappe.logger(__name__).error(f"Email Verification failed because {e}")
        frappe.throw(f"Email Verification failed. {e}")
    # TODO: Add a check to see if employee with email is present, if yes, ask him to login
    # else, enable the employee account


def post_email_verification(name, email, password):
    user_exists = frappe.db.exists("User", {"user_id": email})
    frappe.logger(__name__).info(f"Employee Exists?:{user_exists}")
    # TODO: role arg is not used as of now. By default, setting default roles for new employee
    print("user emaial", name, email)
    try:
        if not user_exists:
            user_doc = frappe.new_doc("User")
            user_doc.update(
                {
                    "first_name": name,
                    "last_name": " ",
                    "name": name,
                    "email": email,
                    "enabled": 1,
                    "send_welcome_email": True,
                }
            )
            user_doc.insert(ignore_permissions=True)
            frappe.logger(__name__).info(f"New User created:  {user_doc.as_dict()}")
            user_doc.add_roles("Website User")
            frappe.db.commit()
        else:
            frappe.throw(f"User with the email {email} already exists, try logging in!")

        # notify sales team on new signup
        # email_template = frappe.render_template(
        #         "observance_app/templates/emails/new_signup.html",
        #         {
        #             "name": name,
        #             "email": email,
        #         },
        #     )
        # frappe.sendmail(
        #     recipients=["sales@the-inkers.com"],
        #     sender="support@the-inkers.com",
        #     reference_doctype="Employee",
        #     reference_name=name,
        #     subject=f"New User Sign-Up - ${name}",
        #     message=email_template,
        #     now=True
        # )
        # create a new frappe bearer token on signup and return the same
        get_token(email, password, new_user=True)

    except Exception as e:
        frappe.logger(__name__).error(
            f"Exception while post_email_verification, {e}, {traceback.format_exc()}"
        )
        traceback.format_exc()
        frappe.throw(traceback.format_exc())
