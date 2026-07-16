# T122 中文规范检查结果记录

## 记录范围

本记录对应 T122，用于固化项目自编写文档、代码注释、文档字符串和示例说明必须使用简体中文的全量检查结果。代码标识符、协议字段、第三方 API 名称和专有技术名词可保留英文。

## 指定检查命令

```powershell
py -3.12 tools/check_chinese_project_text.py
py -3.12 -m pytest -o addopts='' tests/unit/test_chinese_conventions.py -q
```

## 执行结果

本次执行结果：

- `tools/check_chinese_project_text.py`：通过，退出码 0。
- `tests/unit/test_chinese_conventions.py`：`2 passed in 0.51s`，退出码 0。

## 验收结论

当前项目中文规范门禁通过。后续新增或修改项目自编写文档、注释、文档字符串和示例说明时，必须重新运行上述命令；外部 Skill、第三方生成文件或不可安全本地化的外部原文不应被当作项目自编写内容强制改写。
