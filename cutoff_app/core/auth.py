import frappe 
from frappe.utils import random_string, get_url, logger
import frappe
import frappe.oauth
from frappe import _
from frappe.auth import LoginManager
from frappe.utils import cint, get_url, get_datetime
from frappe.utils.password import check_password, passlibctx, update_password



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
                frappe.logger(__name__).debug(
                    f"Checking user password, user: {user}"
                )
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
            "Employee",
            {
                "email": user,
            },
            ["profile_pic", "name", "organization"],
            as_dict=1,
        )
        frappe.logger(__name__).debug(f"user details is {user_details}")
        if user_details is not None:
            frappe.local.response["profile_pic"] = user_details["profile_pic"]
            frappe.local.response["user_id"] = user_details["name"]
            frappe.local.response["organization"] = user_details["organization"]
            org_doc = frappe.get_doc('Organization', user_details['organization'])
            # try reading it from Billing Doctype
            frappe.local.response["pricing_plan"] = org_doc.pricing_plan if org_doc.pricing_plan else None
            frappe.local.response["organization_type"] = org_doc.organization_type if org_doc.organization_type else ""

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
    import jwt
    import frappe.auth
    from oauthlib.oauth2.rfc6749.tokens import random_token_generator, OAuth2Token

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
