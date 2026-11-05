"""Small helpers shared by test modules."""


def set_actor(client, employee_id) -> None:
    """The demo person switcher, as the browser has it after POST /act-as: a signed actor cookie bound to the
    employee logged in on this client."""
    from onboarding import auth
    staff_id = auth.read_session(client.cookies.get(auth.COMPANY_COOKIE), purpose="company")
    client.cookies.set(auth.ACTOR_COOKIE, auth.make_actor(int(employee_id), staff_id))
