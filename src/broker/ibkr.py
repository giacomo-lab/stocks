import urllib.parse
import uuid

from matplotlib.pylab import Any
import requests

from src.broker.base import Broker, Fill, Order, OrderAction


class IBKRBroker(Broker):
    def __init__(
        self,
        host: str = "https://api.ibkr.com",
        account_id: str = "",
        paper_trading: bool = True,
    ):
        self.host = host.rstrip("/")
        self.base_path = "/v1/api"
        self.account_id = account_id
        self.paper_trading = paper_trading
        self._session = requests.Session()
        self._authenticated = False

    def connect(self) -> bool:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/tickle", timeout=10
            )
            resp.raise_for_status()
            self._authenticated = True
            return True
        except requests.RequestException as e:
            print(f"[IBKR] Connection failed: {e}")
            return False

    def authenticate_sso(self, username: str, password: str) -> bool:
        try:
            resp = self._session.post(
                f"{self.host}{self.base_path}/iserver/auth/ssodh/init",
                timeout=10,
            )
            resp.raise_for_status()
            init_data = resp.json()
        except requests.RequestException as e:
            print(f"[IBKR] SSO init failed: {e}")
            return False

        login_data = {
            "LOGIN": username,
            "PASSWORD": password,
            "PAGE": "",
        }
        try:
            resp = self._session.post(
                f"{self.host}{self.base_path}/iserver/auth/ssodh/response",
                json=login_data,
                timeout=10,
            )
            resp.raise_for_status()
            if resp.json().get("authenticated"):
                self._authenticated = True
                return True
            print("[IBKR] Authentication rejected")
            return False
        except requests.RequestException as e:
            print(f"[IBKR] SSO auth failed: {e}")
            return False

    def get_accounts(self) -> list[str]:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/portfolio/accounts", timeout=10
            )
            resp.raise_for_status()
            return [a["accountId"] for a in resp.json()]
        except requests.RequestException as e:
            print(f"[IBKR] Get accounts failed: {e}")
            return []

    def search_contract(self, symbol: str) -> list[dict[Any, Any]]:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/iserver/secdef/search",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[IBKR] Contract search failed: {e}")
            return []

    def get_market_snapshot(self, conids: list[int], fields: list[str]) -> list[dict[Any, Any]]:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/iserver/marketdata/snapshot",
                params={
                    "conids": ",".join(str(c) for c in conids),
                    "fields": ",".join(fields),
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[IBKR] Market snapshot failed: {e}")
            return []

    def get_historical_data(
        self, conid: int, period: str, bar: str = "1d"
    ) -> dict:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/iserver/marketdata/history",
                params={"conid": conid, "period": period, "bar": bar},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[IBKR] Historical data failed: {e}")
            return {}

    def place_order(self, order: Order) -> str:
        order_id = str(uuid.uuid4())
        body = {
            "conid": int(order.ticker) if order.ticker.isdigit() else 0,
            "orderType": order.order_type.value,
            "side": order.action.value,
            "quantity": order.quantity,
            "tif": "DAY",
        }
        if order.limit_price is not None:
            body["price"] = order.limit_price

        try:
            resp = self._session.post(
                f"{self.host}{self.base_path}/iserver/account/{self.account_id}/orders",
                json=body,
                timeout=10,
            )
            resp.raise_for_status()
            return order_id
        except requests.RequestException as e:
            print(f"[IBKR] Order placement failed: {e}")
            return ""

    def cancel_order(self, order_id: str) -> bool:
        try:
            resp = self._session.delete(
                f"{self.host}{self.base_path}/iserver/account/{self.account_id}/orders/{order_id}",
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"[IBKR] Cancel order failed: {e}")
            return False

    def get_positions(self) -> dict:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/portfolio/{self.account_id}/positions/0",
                timeout=10,
            )
            resp.raise_for_status()
            return {pos.get("contractDesc", ""): pos for pos in resp.json()}
        except requests.RequestException as e:
            print(f"[IBKR] Positions request failed: {e}")
            return {}

    def get_cash(self) -> float:
        try:
            resp = self._session.get(
                f"{self.host}{self.base_path}/portfolio/{self.account_id}/summary",
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json():
                if item.get("tag") == "TotalCashValue":
                    return float(item.get("amount", 0))
            return 0.0
        except requests.RequestException as e:
            print(f"[IBKR] Cash query failed: {e}")
            return 0.0

    def disconnect(self) -> bool:
        try:
            self._session.post(f"{self.host}{self.base_path}/logout", timeout=10)
        except requests.RequestException:
            pass
        self._session.close()
        self._authenticated = False
        return True