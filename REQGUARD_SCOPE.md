# ReqGuard Quality Platform — границы проекта № 1

Актуализировано: 04.10.2026. Это проектная спецификация; она не подтверждает реализацию или результаты тестов.

## Цель

Показать воспроизводимый QA Automation / SDET проект: проверка системы UI → API → PostgreSQL → CI, включая AI Quality. Публичный репозиторий, созданный пользователем 23.09.2026: https://github.com/Yeromenko-Kateryna/reqguard-quality-platform. Его текущие файлы, commit и CI требуют отдельной проверки Codex.

## Принятый scope

- Product/evaluator: Python, FastAPI, PostgreSQL, минимальный UI, typed response contracts, deterministic fake AI provider.
- Независимый quality layer: TypeScript + Playwright API/UI, contract/schema tests, SQL/DB assertions, synthetic test data, изоляция и cleanup.
- Воспроизводимость: Docker Compose, CI, run/correlation IDs, отчёты и документированные команды.
- AI Quality: versioned eval dataset, prompt-injection/safety tests, deterministic hard-fail checks, semantic rubrics, human-labelled examples и честное сравнение результатов с порогами.
- Живой AI provider — отдельное позднее решение с ограничением стоимости; default PR проверки не требуют платных вызовов. Зелёный fake provider не доказывает качество живой модели.

## Граница со вторым проектом

Quality Engineering Lab создаётся отдельно и специализируется на performance (k6), accessibility (axe-core) и security baseline (OWASP ZAP). В ReqGuard остаются базовые проверки безопасности собственного продукта: input validation, safe rendering, защита секретов и prompt injection.

## Источники и порядок работы

1. Явные решения пользователя и эта граница задачи.
2. Фактический код, commit, запуски и CI текущего репозитория ReqGuard.
3. Официальная документация инструментов и первичные источники для меняющихся фактов.
4. Аудит QA портфолио от 14.09.2026 — историческая основа замысла, а не результат сегодняшнего запуска.

Существующий `ai-qa-assistant-safety-first-prototype` допускается как источник проверенных идей и кода для осмысленного переноса после инвентаризации. Не превращать его автоматически в текущий репозиторий ReqGuard и не приписывать ReqGuard его тестовые результаты.

## Ближайший gate

Проверить новый репозиторий: HEAD, branch, дерево файлов, текущие инструкции, рабочую копию и доступные проверки. Затем выбрать одну минимальную вертикальную задачу. До такой проверки фактический baseline ReqGuard — UNKNOWN.
