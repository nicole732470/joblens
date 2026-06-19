# JobLens on Lovable

React 应用在仓库 **`web/`**，已接生产 API `http://3.128.164.130:8000`。

---

## 方式 A — 推荐：GitHub 导入

1. 打开 [lovable.dev](https://lovable.dev) 并登录
2. **Create project** → **Import from GitHub**
3. 选仓库 **`nicole732470/joblens`**
4. 若可设子目录：Root directory = **`web`**
5. **Settings → Environment** 添加：
   ```
   VITE_API_URL=http://3.128.164.130:8000
   ```
6. 预览无误后点 **Publish** → 得到 `*.lovable.app` 网址

---

## 方式 B — 本地先验证

```bash
cd web
cp .env.example .env   # 可选
npm install
npm run dev
```

浏览器打开 http://localhost:5173 ，贴 JD → Analyze，应出现 Verdict 卡片。  
确认后再去 Lovable 用方式 A 导入同一套 `web/` 代码。

---

## 方式 C — Lovable AI 从零生成

新建空项目，粘贴此 Prompt：

```
Build a React app "JobLens" — tagline "See a company before you apply".

Design: dark slate header (#0f172a), cyan accent (#0ea5e9), circular "JL" monogram, white result cards.

Form: company, job title, job description textarea, optional resume textarea.

Analyze button POSTs to import.meta.env.VITE_API_URL + "/analyze" with
{ jd_text, company, title, resume_text? }.

Show: recommendation.decision badge (Apply/Near apply/Consider/Skip), reasoning,
sponsorship, resume_fit counts, company fit.

VITE_API_URL=http://3.128.164.130:8000
Loading state (20-60s). No auth.
```

生成后检查 Environment 变量，再 Publish。

---

## API 地址

| 用途 | URL |
|------|-----|
| 弹性 IP | `http://3.128.164.130:8000` |
| AWS 默认 DNS | `http://ec2-3-128-164-130.us-east-2.compute.amazonaws.com:8000` |

CORS 已开放，Lovable 发布的 HTTPS 页面可调用 HTTP API。

---

## 常见问题

- **Analyze 失败**：检查 `VITE_API_URL` 无尾部斜杠；EC2 上 `curl http://3.128.164.130:8000/health`
- **很慢**：免费 LLM；resume embedding 已缓存，不会每次重算
- **H-1B 更全数据**：Chrome Extension 离线 index
