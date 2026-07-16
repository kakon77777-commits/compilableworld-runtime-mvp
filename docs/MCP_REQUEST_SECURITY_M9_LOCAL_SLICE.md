# M9 本地第一切片：Trusted Request Context

## 定位

本地切片建立 Host 到 MCP dispatch 之間的請求上下文與 token primitive 邊界，不宣稱 M9 或 M10 已完成。

已加入：

- `RequestAuthContext`：request id、transport、client 與 peer metadata；
- opaque authorization／session token 欄位；
- `RequestContextProvider`：以 `ContextVar` 綁定單一 dispatch 的 trusted context；
- `REQUEST_CONTEXT_MISSING`、`AUTHORIZATION_MISSING`、`SESSION_TOKEN_MISSING` 與 `INVALID_REQUEST_CONTEXT`；
- 不含秘密值的 `safe_metadata()`；
- 對應 JSON Schema 與單元測試。
- `HMACKeyRing`、`PrincipalTokenCodec`、`SessionTokenCodec` 與 strict Bearer resolver；
- 固定 `HS256`、`kid` 輪替、issuer／audience／lifetime／client scope 驗證；
- Session token 綁定 principal token、world、runtime、timeline、actor 與 role。
- `PrincipalJTIRevocationStore`：process-local 或 SQLite denylist；資料庫只保存 JTI hash；
- `RevocationCheckingPrincipalResolver`：簽章驗證後再檢查撤銷狀態。

## 明確未接入

本切片尚未做：

- JTI 撤銷；
- Rate Limit；
- Reservation／Outbox；
- ASGI、SSE 或 FastMCP middleware；
- `submit_action` 或任何 Runtime 寫入路徑。

目前已完成的是 dependency-free token primitive 與 Principal JTI revoke；尚未接上 HTTP middleware、Session store、Rate Limit 或服務端 session rotation。

## M12 ACL 子邊界

另加入 `WorldACL` 與 `ReadOnlyWorldService(acl=...)` 的本地記憶體整合：開啟 Session 時檢查 user／world／actor／role，每次 Session 讀取時重新檢查。撤銷 grant 會立即使既有 Session 失效。

這不是完整 M12：ACL 尚未持久化，Session refresh／rotation、migration registry 與 runtime ownership lease 尚未接入。

因此現有 M1 read-only MCP 工具的行為不變。下一切片才會把 Host context 綁定接入 Transport adapter，並以測試證明模型不可從 Tool JSON 自行提供 credentials。
