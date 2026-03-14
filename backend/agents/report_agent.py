"""
报告生成 Agent（顶层协调器）
协调 ReportPlanner 和 ReportExecutor，完成报告生成
"""
import uuid
from datetime import datetime
from typing import Dict, Optional, Callable, Any
from pathlib import Path

from backend.models.report import ReportPlan, ChapterResult, ReportExecutionResult
from backend.models.schemas import AnalysisContext
from backend.agents.report_planner import ReportPlanner
from backend.agents.report_executor import ReportExecutor
from backend.services.session_manager import SessionManager
from backend.config import REPORTS_DIR
from backend.utils.chart_builder import ChartBuilder


class ReportAgent:
    """
    报告生成 Agent

    工作流程：
    1. Plan 阶段：ReportPlanner 解析用户意图，生成报告结构
    2. Execute 阶段：ReportExecutor 执行各章节分析
    3. Generate 阶段：生成最终 HTML 报告
    """

    def __init__(
        self,
        session_manager: SessionManager,
        api_key: str = None
    ):
        self.session_manager = session_manager
        self.planner = ReportPlanner(session_manager, api_key)
        self.executor = ReportExecutor(session_manager)

    async def generate_report(
        self,
        session_id: str,
        user_request: str,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        生成完整报告

        :param session_id: 会话 ID
        :param user_request: 用户请求
        :param progress_callback: 进度回调函数 async def callback(progress: Dict)
        :return: report_id
        """
        print(f"[REPORT_AGENT] 开始生成报告，session_id: {session_id}")
        print(f"[REPORT_AGENT] 用户请求：{user_request}")
        try:
            # ========== Phase 1: 创建分析上下文 ==========
            print(f"[REPORT_AGENT] Phase 1: 创建分析上下文")
            if progress_callback:
                await progress_callback({
                    "stage": "planning",
                    "message": "正在读取分析结果...",
                    "progress": 5
                })

            # 从共享存储中读取已有的分析结果
            analysis_results = self.session_manager.get_analysis_results(session_id)
            if not analysis_results:
                print(f"[REPORT_AGENT] 警告：共享存储中没有分析结果，将基于当前数据生成报告")
                analysis_results = {}

            # 获取数据快照
            files = self.session_manager.get_files(session_id)
            data_snapshot = {
                "file_ids": [f.id for f in files],
                "sheet_names": [s.name for f in files for s in f.sheets],
                "row_count": sum(s.row_count for f in files for s in f.sheets),
                "column_count": len(set(c for s in files[0].sheets for c in s.columns)) if files else 0
            }

            # 创建分析上下文
            analysis_context = AnalysisContext(
                request_id=str(uuid.uuid4())[:8],
                user_request=user_request,
                needs_report=True,
                data_snapshot=data_snapshot,
                analysis_summary=analysis_results.get("key_findings", []),
                analysis_results=analysis_results or {}
            )

            # 存储分析上下文
            self.session_manager.store_analysis_context(session_id, analysis_context)

            # ========== Phase 2: 规划 ==========
            print(f"[REPORT_AGENT] Phase 2: 开始规划报告结构")
            if progress_callback:
                await progress_callback({
                    "stage": "planning",
                    "message": "正在分析用户需求，生成报告结构...",
                    "progress": 20
                })

            # 生成报告规划
            plan = await self.planner.plan(session_id, user_request)

            if progress_callback:
                await progress_callback({
                    "stage": "planning",
                    "message": f"报告结构已生成，共 {len(plan.chapters)} 个章节",
                    "progress": 30
                })

            # ========== Phase 3: 执行 ==========
            print(f"[REPORT_AGENT] Phase 3: 开始执行各章节分析")
            if progress_callback:
                await progress_callback({
                    "stage": "executing",
                    "message": "开始执行各章节分析...",
                    "progress": 35
                })

            execution_result = await self.executor.execute(
                plan, session_id, progress_callback
            )

            # ========== Phase 4: 生成 HTML ==========
            print(f"[REPORT_AGENT] Phase 4: 开始生成 HTML 报告")
            if progress_callback:
                await progress_callback({
                    "stage": "generating",
                    "message": "正在生成 HTML 报告...",
                    "progress": 85
                })

            report_id = self._generate_html_report(
                session_id, plan, execution_result
            )
            print(f"[REPORT_AGENT] HTML 报告生成完成，report_id: {report_id}")

            # 更新会话的报告 ID
            self.session_manager.set_report_id(session_id, report_id)

            if progress_callback:
                await progress_callback({
                    "stage": "complete",
                    "message": "报告生成完成！",
                    "progress": 100,
                    "report_id": report_id
                })

            return report_id

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[REPORT_AGENT] 报告生成失败：{e}")
            print(f"[REPORT_AGENT] 错误详情：{error_detail}")
            if progress_callback:
                await progress_callback({
                    "stage": "error",
                    "message": f"报告生成失败：{str(e)}",
                    "progress": 0
                })
            raise

    def _generate_html_report(
        self,
        session_id: str,
        plan: ReportPlan,
        execution_result: Dict
    ) -> str:
        """生成 HTML 报告"""
        report_id = str(uuid.uuid4())[:8]

        # 获取所有章节结果
        chapter_results = self.session_manager.get_all_chapter_results(session_id)

        # 生成 HTML 内容
        html_content = self._build_html_content(plan, chapter_results, session_id)

        # 保存报告
        report_path = REPORTS_DIR / f"{report_id}.html"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return report_id

    def _build_html_content(
        self,
        plan: ReportPlan,
        chapter_results: Dict[str, ChapterResult],
        session_id: str
    ) -> str:
        """构建 HTML 报告内容"""
        # 生成章节 HTML
        chapters_html = ""
        chapters_nav = ""

        for chapter in plan.chapters:
            result = chapter_results.get(chapter.id)

            # 导航目录
            chapters_nav += f'<li><a href="#{chapter.id}">{chapter.title}</a></li>\n'

            # 章节内容
            chapter_html = self._render_chapter(chapter, result)
            chapters_html += chapter_html

        # 生成时间
        from datetime import datetime
        generated_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 完整的 HTML 报告 - 使用占位符，避免与 CSS 中的 { } 冲突
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__PLAN_TITLE__</title>
    <script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            display: flex;
            min-height: 100vh;
        }
        /* 侧边导航栏 */
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            width: 250px;
            height: 100vh;
            background: #1a1a2e;
            color: #fff;
            padding: 20px 0;
            overflow-y: auto;
            z-index: 1000;
        }
        .sidebar-header {
            padding: 0 20px 20px;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }
        .sidebar-header h2 {
            font-size: 1.2rem;
            color: #667eea;
        }
        .sidebar-nav ul {
            list-style: none;
        }
        .sidebar-nav li {
            margin: 0;
        }
        .sidebar-nav a {
            display: block;
            padding: 12px 20px;
            color: #aaa;
            text-decoration: none;
            transition: all 0.3s;
            font-size: 0.9rem;
        }
        .sidebar-nav a:hover {
            background: #16213e;
            color: #fff;
        }
        .sidebar-nav li.active a {
            background: #667eea;
            color: #fff;
        }
        /* 主内容区 */
        .main-content {
            margin-left: 250px;
            flex: 1;
            padding: 30px;
        }
        .report-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        .report-header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }
        .report-header .meta {
            opacity: 0.9;
            font-size: 0.9rem;
        }
        .section {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            scroll-margin-top: 20px;
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
            font-size: 1.4rem;
        }
        .section h3 {
            color: #555;
            margin: 15px 0 10px;
            font-size: 1.1rem;
        }
        .section-content {
            color: #666;
            line-height: 1.8;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid #dee2e6;
        }
        .stat-card .value {
            font-size: 1.8rem;
            font-weight: bold;
            color: #667eea;
        }
        .stat-card .label {
            color: #666;
            font-size: 0.85rem;
            margin-top: 8px;
        }
        .insights {
            background: #f0f4ff;
            border-left: 4px solid #667eea;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }
        .insights li {
            margin: 8px 0;
            color: #555;
        }
        .chart-container {
            margin: 25px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 10px;
            border: 1px solid #eee;
        }
        .chart-container h3 {
            margin-bottom: 15px;
            color: #444;
        }
        .data-view-btn {
            display: inline-block;
            margin-top: 10px;
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.3s;
        }
        .data-view-btn:hover {
            background: #5568d3;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #555;
        }
        tr:hover {
            background: #f8f9fa;
        }
        /* 响应式设计 */
        @media (max-width: 768px) {
            .sidebar {
                transform: translateX(-100%);
                transition: transform 0.3s;
            }
            .sidebar.open {
                transform: translateX(0);
            }
            .main-content {
                margin-left: 0;
            }
            .mobile-menu-btn {
                display: block;
                position: fixed;
                top: 15px;
                left: 15px;
                z-index: 1001;
                padding: 10px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }
        }
        @media (min-width: 769px) {
            .mobile-menu-btn {
                display: none;
            }
        }
        /* 数据弹窗 */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 2000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.show {
            display: flex;
        }
        .modal-container {
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 1000px;
            max-height: 85vh;
            display: flex;
            flex-direction: column;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
        }
        .modal-header h3 {
            margin: 0;
            color: #333;
        }
        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #999;
        }
        .modal-close:hover {
            color: #333;
        }
        .modal-body {
            flex: 1;
            overflow: auto;
            padding: 20px;
        }
        .data-table {
            width: 100%;
            font-size: 0.9rem;
        }
        .data-table th {
            position: sticky;
            top: 0;
            background: #f8f9fa;
            z-index: 1;
        }
    </style>
</head>
<body>
    <button class="mobile-menu-btn" onclick="toggleSidebar()">☰ 目录</button>

    <aside class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h2>📊 报告目录</h2>
        </div>
        <nav class="sidebar-nav">
            <ul>
                __CHAPTERS_NAV__
            </ul>
        </nav>
    </aside>

    <main class="main-content">
        <div class="report-header">
            <h1>__PLAN_TITLE__</h1>
            <div class="meta">
                <p>分析主题：__PLAN_THEME__</p>
                <p>生成时间：__GENERATED_TIME__</p>
            </div>
        </div>

        __CHAPTERS_HTML__
    </main>

    <!-- 数据查看弹窗 -->
    <div class="modal-overlay" id="dataModal" onclick="closeModal(event)">
        <div class="modal-container">
            <div class="modal-header">
                <h3 id="modalTitle">原始数据</h3>
                <button class="modal-close" onclick="closeModalBtn()">×</button>
            </div>
            <div class="modal-body">
                <div id="modalContent"></div>
            </div>
        </div>
    </div>

    <script>
        // 侧边栏高亮当前章节
        const sections = document.querySelectorAll('.section');
        const navLinks = document.querySelectorAll('.sidebar-nav a');

        function highlightNav() {
            let currentSection = '';
            sections.forEach(section => {
                const sectionTop = section.offsetTop - 100;
                const sectionBottom = sectionTop + section.offsetHeight;
                if (window.scrollY >= sectionTop && window.scrollY < sectionBottom) {
                    currentSection = section.id;
                }
            });

            navLinks.forEach(link => {
                link.parentElement.classList.remove('active');
                if (link.getAttribute('href') === '#' + currentSection) {
                    link.parentElement.classList.add('active');
                }
            });
        }

        window.addEventListener('scroll', highlightNav);
        highlightNav();  // 初始化

        // 点击导航平滑滚动
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = link.getAttribute('href').substring(1);
                const target = document.getElementById(targetId);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth' });
                    // 移动端自动关闭侧边栏
                    if (window.innerWidth <= 768) {
                        document.getElementById('sidebar').classList.remove('open');
                    }
                }
            });
        });

        // 移动端切换侧边栏
        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
        }

        // ========== 图表懒加载 - Intersection Observer ==========
        const chartObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const container = entry.target;
                    const chartHtmlDiv = container.querySelector('.chart-html');
                    const placeholder = container.querySelector('.chart-placeholder');
                    if (chartHtmlDiv && placeholder) {
                        try {
                            // 获取隐藏的图表 HTML
                            const chartHtml = chartHtmlDiv.innerHTML;
                            // 显示占位符
                            placeholder.innerHTML = '<div style="font-size:24px;margin-bottom:10px;">📊</div><div>正在渲染图表...</div>';
                            // 将图表 HTML 插入到容器中
                            chartHtmlDiv.style.display = 'block';
                            // 执行图表 HTML 中的脚本
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = chartHtml;
                            const scripts = tempDiv.querySelectorAll('script');
                            scripts.forEach(script => {
                                const newScript = document.createElement('script');
                                if (script.src) {
                                    newScript.src = script.src;
                                } else if (script.textContent) {
                                    newScript.textContent = script.textContent;
                                }
                                chartHtmlDiv.appendChild(newScript);
                            });
                            // 移除占位符
                            placeholder.style.display = 'none';
                            // 图表渲染完成后停止观察
                            chartObserver.unobserve(container);
                        } catch (e) {
                            console.error('图表渲染失败:', e);
                            placeholder.innerHTML = '图表加载失败，请刷新页面重试';
                        }
                    }
                }
            });
        }, {
            rootMargin: '100px',  // 提前 100px 开始加载
            threshold: 0.01
        });

        // 初始化图表懒加载
        function initChartLazyLoad() {
            document.querySelectorAll('.chart-container').forEach(container => {
                chartObserver.observe(container);
            });
        }

        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', initChartLazyLoad);

        // 数据弹窗
        function showDataModal(title, data) {
            document.getElementById('modalTitle').textContent = title;
            const content = document.getElementById('modalContent');

            if (Array.isArray(data) && data.length > 0) {
                // 渲染表格
                const keys = Object.keys(data[0]);
                let html = '<table class="data-table"><thead><tr>';
                keys.forEach(k => html += '<th>' + k + '</th>');
                html += '</tr></thead><tbody>';
                data.forEach(row => {
                    html += '<tr>';
                    keys.forEach(k => html += '<td>' + (row[k] !== null ? row[k] : '') + '</td>');
                    html += '</tr>';
                });
                html += '</tbody></table>';
                html += '<p style="margin-top:15px;color:#666;">共 ' + data.length + ' 条数据</p>';
                content.innerHTML = html;
            } else {
                content.innerHTML = '<p>暂无数据</p>';
            }

            document.getElementById('dataModal').classList.add('show');
        }

        function closeModal(event) {
            if (event.target.id === 'dataModal') {
                document.getElementById('dataModal').classList.remove('show');
            }
        }

        function closeModalBtn() {
            document.getElementById('dataModal').classList.remove('show');
        }

        // 图表点击事件处理 - 查看原始数据
        function attachChartClickEvents() {
            // 遍历所有 pyecharts 容器，绑定点击事件
            document.querySelectorAll('.chart-container').forEach(container => {
                // pyecharts 图表渲染后会自带 click 事件，这里可以通过自定义事件来处理
                // 由于 pyecharts 的交互是内置的，我们在后端生成图表时可以添加自定义事件
            });
        }

        attachChartClickEvents();
    </script>
</body>
</html>
"""
        # 使用安全的字符串替换方式，避免 CSS 中的 { } 干扰
        html = html_template.replace("__PLAN_TITLE__", plan.title)\
                           .replace("__PLAN_THEME__", plan.theme)\
                           .replace("__GENERATED_TIME__", generated_time)\
                           .replace("__CHAPTERS_NAV__", chapters_nav)\
                           .replace("__CHAPTERS_HTML__", chapters_html)
        return html

    def _render_chapter(self, chapter, result: Optional[ChapterResult]) -> str:
        """渲染单个章节"""
        if not result or not result.success:
            error_msg = result.error if result else "分析失败"
            return f"""
            <div class="section" id="{chapter.id}">
                <h2>{chapter.title}</h2>
                <p class="section-content">本章分析失败：{error_msg}</p>
            </div>
            """

        # 构建章节内容
        content_parts = []

        # 描述
        if result.description:
            content_parts.append(f'<p class="section-content">{result.description}</p>')

        # 数据摘要
        if result.data:
            if result.analysis_type == "overview":
                content_parts.append(self._render_overview_data(result.data))
            elif result.analysis_type == "ranking":
                content_parts.append(self._render_ranking_data(result.data))
            elif result.analysis_type == "distribution":
                content_parts.append(self._render_distribution_data(result.data))
            elif result.analysis_type == "trend":
                content_parts.append(self._render_trend_data(result.data))
            elif result.analysis_type == "comparison":
                content_parts.append(self._render_comparison_data(result.data))
            elif result.analysis_type == "correlation":
                content_parts.append(self._render_correlation_data(result.data))

        # 洞察
        if result.insights:
            insights_html = '<div class="insights"><strong>💡 洞察：</strong><ul>'
            for insight in result.insights:
                insights_html += f'<li>{insight}</li>'
            insights_html += '</ul></div>'
            content_parts.append(insights_html)

        # 图表
        if result.chart_spec:
            chart_html = self._render_chart(result)
            content_parts.append(chart_html)

        return f"""
        <div class="section" id="{chapter.id}">
            <h2>{chapter.title}</h2>
            {''.join(content_parts)}
        </div>
        """

    def _render_overview_data(self, data: Dict) -> str:
        """渲染概览数据"""
        stats = []
        stats.append(f'<div class="stat-card"><div class="value">{data.get("row_count", 0):,}</div><div class="label">总行数</div></div>')
        stats.append(f'<div class="stat-card"><div class="value">{data.get("column_count", 0)}</div><div class="label">列数</div></div>')
        stats.append(f'<div class="stat-card"><div class="value">{len(data.get("numeric_columns", []))}</div><div class="label">数值列</div></div>')
        stats.append(f'<div class="stat-card"><div class="value">{len(data.get("categorical_columns", []))}</div><div class="label">分类列</div></div>')

        return f"""
        <h3>数据概览</h3>
        <div class="stats-grid">
            {''.join(stats)}
        </div>
        """

    def _render_ranking_data(self, data: Dict) -> str:
        """渲染排名数据"""
        ranking = data.get("ranking", {})
        if not ranking:
            return "<p>暂无排名数据</p>"

        rows = ""
        for i, (item, value) in enumerate(list(ranking.items())[:10], 1):
            rows += f"<tr><td>{i}</td><td>{item}</td><td>{value}</td></tr>"

        return f"""
        <h3>排名数据</h3>
        <table>
            <thead><tr><th>排名</th><th>项目</th><th>数值</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """

    def _render_distribution_data(self, data: Dict) -> str:
        """渲染分布数据"""
        dist = data.get("distribution", {})
        total = data.get("total", 1)

        rows = ""
        for item, count in list(dist.items())[:15]:
            pct = (count / total) * 100
            rows += f"<tr><td>{item}</td><td>{count:,}</td><td>{pct:.1f}%</td></tr>"

        return f"""
        <h3>分布数据</h3>
        <table>
            <thead><tr><th>项目</th><th>数量</th><th>占比</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """

    def _render_trend_data(self, data: Dict) -> str:
        """渲染趋势数据"""
        trend = data.get("trend", {})
        if not trend:
            return "<p>暂无趋势数据</p>"

        rows = ""
        for period, value in list(trend.items())[:20]:
            rows += f"<tr><td>{period}</td><td>{value:,}</td></tr>"

        return f"""
        <h3>趋势数据</h3>
        <table>
            <thead><tr><th>时间/周期</th><th>数值</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """

    def _render_comparison_data(self, data: Dict) -> str:
        """渲染对比数据"""
        comparison = data.get("comparison", {})
        if not comparison:
            return "<p>暂无对比数据</p>"

        if data.get("type") == "numeric":
            rows = ""
            metrics = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
            for metric in metrics:
                if metric in comparison:
                    rows += f"<tr><td>{metric}</td><td>{comparison[metric]:,.2f}</td></tr>"
            return f"""
            <h3>统计摘要</h3>
            <table>
                <tbody>{rows}</tbody>
            </table>
            """
        else:
            rows = ""
            for item, count in list(comparison.items())[:15]:
                rows += f"<tr><td>{item}</td><td>{count:,}</td></tr>"
            return f"""
            <h3>分类对比</h3>
            <table>
                <thead><tr><th>类别</th><th>数量</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            """

    def _render_correlation_data(self, data: Dict) -> str:
        """渲染相关性数据"""
        columns = data.get("columns", [])
        return f"""
        <h3>相关性分析</h3>
        <p>分析变量：{', '.join(columns[:10])}</p>
        <p>详见下方热力图可视化</p>
        """

    def _render_chart(self, result: ChapterResult) -> str:
        """渲染图表（支持懒加载）"""
        if not result.chart_spec:
            return ""

        chart_spec = result.chart_spec
        chart_type = chart_spec.get("type", "bar")
        chart_data = chart_spec.get("data", {})
        title = chart_spec.get("title", "图表")

        # 使用 ChartBuilder 生成图表
        chart = None
        if chart_type == "bar" and chart_data:
            chart = ChartBuilder.create_bar_chart(chart_data, title)
        elif chart_type == "line" and chart_data:
            chart = ChartBuilder.create_line_chart(chart_data, title)
        elif chart_type == "pie" and chart_data:
            chart = ChartBuilder.create_pie_chart(chart_data, title)
        elif chart_type == "heatmap" and chart_data:
            chart = ChartBuilder.create_heatmap(chart_data, title)

        if not chart:
            return ""

        # 生成查看数据按钮的 JavaScript
        chart_id = f"chart-{result.chapter_id}"
        data_field = result.data.get("dimension") if result.data else None

        # 将数据编码为 JSON 嵌入到页面
        import json
        view_data_script = ""
        if data_field:
            raw_data = json.dumps(list(result.data.get("raw_sample", []))[:100], ensure_ascii=False)
            view_data_script = f"""
            <button class="data-view-btn" onclick="showDataModal('{title} - 原始数据', {raw_data})">
                📊 查看原始数据
            </button>
            """

        # 懒加载容器：图表 HTML 存储在隐藏的 div 中，由 JS 懒加载渲染
        chart_html = chart['html']
        return f"""
        <div class="chart-container" id="{chart_id}">
            <h3>{title}</h3>
            <div class="chart-placeholder" style="text-align:center;padding:40px;color:#999;">
                <div style="font-size:24px;margin-bottom:10px;">📊</div>
                <div>图表加载中...</div>
            </div>
            <div class="chart-html" style="display:none;">{chart_html}</div>
            {view_data_script}
        </div>
        """

    @staticmethod
    def read_report(report_id: str) -> Optional[str]:
        """读取报告内容"""
        from backend.config import REPORTS_DIR
        from pathlib import Path

        report_path = REPORTS_DIR / f"{report_id}.html"
        if not report_path.exists():
            return None

        with open(report_path, 'r', encoding='utf-8') as f:
            return f.read()
