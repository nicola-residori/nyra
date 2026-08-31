# Device-local secrets

`tools/new-speaker.py` creates one private YAML file per speaker here, for example:

```yaml
api_encryption_key: "..."
ota_password: "..."
```

These files are injected as ESPHome substitutions by the top-level device entrypoint and are intentionally ignored by Git. Never commit real files from this directory.
