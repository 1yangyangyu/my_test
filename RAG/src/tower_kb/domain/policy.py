from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

def allowed(version, actor):
    return (version["org_id"] == actor.org_id
            and version["status"] == "PUBLISHED"
            and not version["deleted"]
            and version["current_version"] == version["version"]
            and bool(set(version["roles"]) & set(actor.roles))
            and bool(set(version["regions"]) & set(actor.regions))
            and (not version["effect_start"] or version["effect_start"] <= now())
            and (not version["effect_end"] or now() < version["effect_end"]))
