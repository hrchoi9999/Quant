from __future__ import annotations

from flask import Flask, jsonify, render_template

from service_platform.web.data_provider import SnapshotProvider

app = Flask(__name__)
provider = SnapshotProvider()


@app.route('/')
def home():
    return render_template('home.html', payload=provider.load_home_payload())


@app.route('/today')
def today():
    return render_template('today.html', payload=provider.load_today_payload())


@app.route('/performance')
def performance():
    return render_template('performance.html', payload=provider.load_performance_payload())


@app.route('/changes')
def changes():
    return render_template('changes.html', payload=provider.load_changes_payload())


@app.route('/api/v1/manifest')
def api_manifest():
    return jsonify(provider.load_manifest())


@app.route('/api/v1/user-models')
def api_user_models():
    return jsonify(provider.load_catalog())


@app.route('/api/v1/model-snapshots/today')
def api_model_snapshot_today():
    return jsonify(provider.load_today_payload())


@app.route('/api/v1/model-snapshots/<service_profile>')
def api_model_snapshot_profile(service_profile: str):
    return jsonify(provider.load_recommendation_by_profile(service_profile))


@app.route('/api/v1/recommendation/today')
def api_recommendation_today_legacy():
    return jsonify(provider.load_today_payload())


@app.route('/api/v1/recommendation/<service_profile>')
def api_recommendation_profile_legacy(service_profile: str):
    return jsonify(provider.load_recommendation_by_profile(service_profile))


@app.route('/api/v1/performance/summary')
def api_performance_summary():
    return jsonify(provider.load_performance_payload())


@app.route('/api/v1/changes/recent')
def api_changes_recent():
    return jsonify(provider.load_changes_payload())


if __name__ == '__main__':
    app.run(debug=True, port=5080)

