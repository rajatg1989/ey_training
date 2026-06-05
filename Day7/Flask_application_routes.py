# src/app/routes.py
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from .models import CustomerRecord
from .service import CustomerService

api_bp = Blueprint("api", __name__)
svc = CustomerService()

@api_bp.route("/customers", methods=["POST"])
def create_customer():
    try:
        payload = CustomerRecord(
            **request.get_json())
    except ValidationError as e:
        return jsonify(
            {"errors": e.errors()}), 422
    result = svc.create(payload)
    return jsonify(result.dict()), 201

@api_bp.route(
    "/customers/<cid>", methods=["GET"])
def get_customer(cid: str):
    rec = svc.get(cid)
    if not rec:
        return jsonify(
            {"error": "Not found"}), 404
    return jsonify(rec.dict()), 200
