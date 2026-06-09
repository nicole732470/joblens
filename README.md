# LCA Sponsor Checker

在 LinkedIn 公司页自动查询该公司是否出现在 **DOL H-1B LCA Disclosure** 数据中。

打开 `linkedin.com/company/...` 时，插件从 URL slug 匹配本地 LCA 雇主索引，在页面右上角显示 badge（LCA 数量、H-1B 数量、Certified 比例、常见岗位）。

## 项目结构

```
.
├── convert_to_sqlite.py          # Excel → SQLite（本地数据处理）
├── export_employer_index.py      # SQLite → 插件用 JSON/Gzip 索引
├── slug_overrides.json           # LinkedIn slug → FEIN 手工映射
├── requirements.txt
├── chrome-extension/             # Chrome 插件（Manifest V3）
│   ├── manifest.json
│   ├── content.js
│   ├── styles.css
│   ├── lib/matcher.js
│   └── data/employers.json.gz    # 预构建索引（~7MB）
└── README.md
```

> **注意：** 原始 Excel（~440MB）和 SQLite（~940MB）体积过大，**不包含在 Git 仓库中**。请自行从 DOL 下载 LCA 数据后本地转换，或使用仓库内已提交的 `employers.json.gz` 直接使用插件。

## 快速开始（只用插件）

1. 克隆仓库
2. Chrome 打开 `chrome://extensions`
3. 开启 **开发者模式**
4. **加载已解压的扩展程序** → 选择 `chrome-extension/` 文件夹
5. 打开任意 LinkedIn 公司页，例如：
   - https://www.linkedin.com/company/microsoft/
   - https://www.linkedin.com/company/typeface/

## 更新数据（完整流程）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 下载 LCA Excel

从 DOL 下载 LCA Disclosure 数据，放到项目根目录，默认文件名：

`LCA_Dislclosure_Data_FY2026_Q2.xlsx`

如需更换文件，修改 `convert_to_sqlite.py` 中的 `XLSX_PATH`。

### 3. Excel → SQLite

```bash
python3 convert_to_sqlite.py
```

约 1–2 分钟，生成 `lca_fy2026_q2.db`。

### 4. 导出插件索引

```bash
python3 export_employer_index.py
```

生成 `chrome-extension/data/employers.json.gz`。

### 5. 测试匹配

```bash
python3 export_employer_index.py --test microsoft
python3 export_employer_index.py --test dun-bradstreet
python3 export_employer_index.py --test typeface
```

### 6. 重载插件

在 `chrome://extensions` 点击插件的 **重新加载** 按钮。

## 匹配逻辑

1. 从 URL 提取 slug（如 `linkedin.com/company/google/` → `google`）
2. 查 `slug_overrides.json` 手工映射（如 `dun-bradstreet` → Dun & Bradstreet FEIN）
3. 在预构建 `key_index` 中精确匹配
4. 失败则读页面 `h1` 公司名再匹配
5. 最后做 substring 模糊匹配（按 LCA 数量取最高）

## 数据来源

- **LCA 数据：** [DOL Office of Foreign Labor Certification](https://www.dol.gov/agencies/eta/foreign-labor/performance)
- **数据周期：** FY2026 Q2（脚本默认）
- **索引规模：** 74,732 家公司（按 FEIN 去重），806,939 条 LCA

## 常见问题

**Q: 为什么 LinkedIn 有公司但插件显示未找到？**

公司法定名与 LinkedIn slug 不一致，或该公司确实未 file LCA。可在 `slug_overrides.json` 添加映射。

**Q: LCA 有记录 = 一定招 H-1B 吗？**

不是。LCA 是合规备案，可能是续签、transfer 或 amendment。仅作参考。

**Q: 插件需要联网吗？**

不需要。查询完全在本地浏览器内完成（读取打包的 `employers.json.gz`）。

## License

MIT — 数据版权归美国劳工部（DOL），请遵守其公开数据使用条款。
