from __future__ import annotations
import argparse,getpass
from pathlib import Path
from backend.external_observation.policy import InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyStore
from backend.secrets import WindowsCredentialManagerSecretStore
from .yandex_mail.config import YandexMailConfig,YandexMailConfigStore,YANDEX_MAIL_CLIENT_SECRET_REF,YANDEX_MAIL_SECRET_REF
from .yandex_mail.oauth import authorize
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--project-root",type=Path,default=Path.cwd());c=p.add_subparsers(dest="command",required=True);connect=c.add_parser("connect");connect.add_argument("--client-id",required=True);connect.add_argument("--email",required=True);c.add_parser("status");c.add_parser("disconnect");a=p.parse_args(argv);store=YandexMailConfigStore(a.project_root/"local-data/config/yandex-mail.json");secrets=WindowsCredentialManagerSecretStore()
 if a.command=="status":print("DISCONNECTED" if store.load() is None else store.load().credential_state(secrets).value.upper());return 0
 if a.command=="disconnect":
  cfg=store.load();secrets.delete(YANDEX_MAIL_SECRET_REF if cfg is None else cfg.secret_ref);secrets.delete(YANDEX_MAIL_CLIENT_SECRET_REF if cfg is None else cfg.client_secret_ref);store.delete();print("DISCONNECTED");return 0
 secret=getpass.getpass("Yandex OAuth client secret: ");cfg=YandexMailConfig(client_id=a.client_id,account_email=a.email);tokens=authorize(client_id=cfg.client_id,client_secret=secret,code_prompt=lambda _:getpass.getpass("Yandex authorization code: "),policy_store=InternetAccessPolicyStore(a.project_root/"local-data/config/internet-access.json"),safety_store=AutonomySafetyStore(a.project_root/"local-data/config/autonomy-safety.json"));refresh=tokens.get("refresh_token")
 if not isinstance(refresh,str) or not refresh:raise RuntimeError("yandex_refresh_token_missing")
 secrets.put(cfg.client_secret_ref,secret);secrets.put(cfg.secret_ref,refresh);store.save(cfg);print("READY");return 0
if __name__=="__main__":raise SystemExit(main())
