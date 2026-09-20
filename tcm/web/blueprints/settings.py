from flask import Blueprint, jsonify, request

from tcm.services import settings_store as config_store

bp = Blueprint("settings", __name__)

# --- the editable configs --------------------------------------------------
#
# `jsonify` wrappers around `config_store`, the same arrangement as the
# aggregate and prepare endpoints. The rules — what validates, what is written,
# what takes effect — are the store's; what stays here is the request.


@bp.route("/api/config")
def get_config():
    """GET /api/config - every editable config file, and the vocabularies.

    The vocabularies (tones, derive conditions, the sheet-label field names)
    come down with the data so the editor never writes its own copy of a list
    the validator would then refuse.
    """
    return jsonify(config_store.read_all())


@bp.route("/api/config/<name>", methods=["PUT"])
def put_config(name):
    """PUT /api/config/<name> - validate `{"data": {...}}`, save it, apply it.

    A refused edit changes nothing: the store validates before it writes, so a
    400 here means the file on disk and the running app are both as they were.
    The message is the config class's own, because it names the invariant that
    was broken rather than saying the edit was bad.
    """
    if name not in config_store.CONFIGS:
        return jsonify({
            "error": f"Unknown config '{name}'; "
                     f"expected one of {', '.join(sorted(config_store.CONFIGS))}"
        }), 404

    body = request.get_json(silent=True) or {}
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"error": "Provide 'data' as the config object to save"}), 400

    try:
        saved = config_store.save(name, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        return jsonify({"error": f"Could not write the config file: {e}"}), 500

    return jsonify(saved), 200
