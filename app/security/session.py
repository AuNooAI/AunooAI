from fastapi import Request, HTTPException, status

def verify_session(request: Request):
    if not request.session.get("user"):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return request.session 