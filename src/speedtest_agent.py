from fastapi import FastAPI, HTTPException
import subprocess

app = FastAPI()

@app.get("/speedtest")
def run_speedtest():
    try:
        result = subprocess.check_output(
            ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json"],
            timeout=60
        )
        return {"status": "ok", "data": result.decode()}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Speedtest timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
