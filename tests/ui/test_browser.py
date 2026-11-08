"""Real Edge DOM journeys with synthetic HTTP fixtures; no browser dependencies."""

import json
import os
import subprocess
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src/bottleneck_analyzer/api/static"
EDGE = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / (
    "Microsoft/Edge/Application/msedge.exe"
)


def browser_result(outcome="completed"):
    return {
        "outcome": outcome,
        "answer": "Synthetic browser fixture",
        "scope": {"dataset": "fixture"},
        "clarification": "Select a method" if outcome == "clarification_required" else None,
        "historical": {
            "historical_jph": 46.88,
            "design_gap_jph": 13.12,
            "leading_candidate": "Hemming",
            "evidence_strength": "strong",
            "supporting_indicators": [
                "High processing/fault occupancy: 0.9998",
                "Input queue accumulation: 0.9826",
                "Upstream blocking: 0.2667",
                "Downstream starvation: 0.2799",
            ],
            "conflicting_indicators": [],
            "aggregate_ids": [],
            "candidate_changes": [],
            "segments": [],
            "completed": 21096,
            "scheduled_hours": 450,
        },
        "evidence": {
            "methods_run": ["exact", "lexical", "semantic"],
            "unavailable_methods": [],
            "warnings": [],
            "interpretations": [],
            "records": [
                {
                    "source_system": "CMMS",
                    "source_id": "TEST-1",
                    "station": "Hemming",
                    "relationship": "inferred",
                    "relationship_basis": "same station/time",
                    "document_version": "v1",
                    "text": '<img src=x onerror="window.injected=true">untrusted source'
                    + " Original source passage." * 40,
                }
            ],
        },
        "simulation": {
            "baseline": {"mean": 46.255889, "ci95": [46, 47], "n": 20},
            "scenario": {"mean": 49.609, "ci95": [49, 50], "n": 20},
            "paired_gain": {"mean": 3.353111, "ci95": [3.2, 3.5], "n": 20},
            "days": 30,
            "configuration_version": "fixture",
        },
        "interpretation": None,
        "warnings": ["Synthetic fixture"],
        "limitations": [],
        "errors": [],
        "projection_notices": [],
        "human_review": "Human review required",
    }


DRIVER = Path(__file__).with_name("browser-driver.mjs").read_text(encoding="utf-8")

CAPTURE = """
window.__browserErrors = [];
window.addEventListener('error', event => window.__browserErrors.push(
  event.message || 'Asset failed: ' + (event.target.src || event.target.href)), true);
window.addEventListener('unhandledrejection', event =>
  window.__browserErrors.push(String(event.reason)));
const originalError = console.error;
console.error = (...args) => {
  window.__browserErrors.push(args.join(' ')); originalError(...args);
};
"""


def screenshot_path(tmp_path, name):
    directory = Path(os.getenv("UI_SCREENSHOT_DIR", str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve() / name


def capture_browser(tmp_path, url, width, height, name, marker):
    profile = tmp_path / name
    profile.mkdir()
    with (tmp_path / (name + ".log")).open("wb") as log:
        browser = subprocess.Popen(
            [
                str(EDGE),
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={profile}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=log,
        )
        try:
            port_file = profile / "DevToolsActivePort"
            deadline = time.monotonic() + 15
            port = None
            while port is None:
                assert time.monotonic() < deadline, "Edge debugging endpoint unavailable"
                try:
                    port = int(port_file.read_text(encoding="utf-8").splitlines()[0])
                except (OSError, ValueError, IndexError):
                    pass  # Windows can expose the file before Edge releases its write handle.
                time.sleep(0.02)
            env = os.environ.copy()
            env["UI_CDP_CONFIG"] = json.dumps(
                {
                    "port": port,
                    "width": width,
                    "height": height,
                    "url": url,
                    "screenshot": str(screenshot_path(tmp_path, name + ".png")),
                    "marker": marker,
                }
            )
            result = subprocess.run(
                ["node", str(Path(__file__).with_name("browser-driver.mjs"))],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=55,
            )
            assert result.returncode == 0, result.stderr[-3000:]
            data = json.loads(result.stdout)
            screenshot_path(tmp_path, name + ".json").write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            assert data["viewport"] == {"width": width, "height": height, "overflow": False}
            assert not data["errors"], data["errors"]
            assert data["focus"]["tag"] in ("A", "BUTTON", "SUMMARY", "INPUT", "SELECT", "TEXTAREA")
            assert data["focus"]["outline"] != "none"
            assert data["keyboardEvidence"], "Enter did not toggle evidence details"
            assert any(a["mime"] == "text/css" and a["status"] == 200 for a in data["assets"])
            assert all(a["status"] == 200 for a in data["assets"])
            failure = data["dom"].split('data-browser-error="')
            assert data["status"] == "passed", (
                failure[1].split('"')[0] if len(failure) > 1 else data["dom"][-3000:]
            )
            return data["dom"]
        finally:
            if browser.poll() is None:
                browser.terminate()
            browser.wait(timeout=10)


@pytest.mark.skipif(not EDGE.exists(), reason="Existing Microsoft Edge executable unavailable")
@pytest.mark.parametrize("width,height", [(1440, 1200), (390, 1000)])
def test_browser_question_groups_outcomes_evidence_and_refresh(tmp_path, width, height):
    from fastapi.testclient import TestClient

    from bottleneck_analyzer.main import app

    asset_client = TestClient(app, base_url="http://127.0.0.1:8000")
    state = {"posts": 0, "rows": {}, "last": None, "requests": [], "keys": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, content, mime="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; object-src 'none'",
            )
            self.end_headers()
            self.wfile.write(content if isinstance(content, bytes) else content.encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                return self.send(
                    (STATIC / "index.html")
                    .read_text(encoding="utf-8")
                    .replace(
                        '<script type="module"',
                        '<script src="/capture.mjs"></script><script type="module"',
                        1,
                    )
                    .replace("</body>", '<script type="module" src="/driver.mjs"></script></body>'),
                    "text/html",
                )
            if path == "/driver.mjs":
                return self.send(DRIVER, "text/javascript")
            if path == "/capture.mjs":
                return self.send(CAPTURE, "text/javascript")
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path.startswith("/static/"):
                response = asset_client.get(path)
                assert response.status_code == 200
                if path.endswith(".css"):
                    assert response.headers["content-type"].split(";")[0] == "text/css"
                return self.send(
                    response.content,
                    response.headers["content-type"],
                )
            if path == "/__stats":
                return self.send(
                    json.dumps({"posts": state["posts"], "requests": state["requests"]})
                )
            if path == "/api/datasets":
                return self.send(
                    json.dumps(
                        [
                            {
                                "id": "fixture",
                                "name": "fixture",
                                "provenance": "authored_fixture",
                                "start_time": "2026-09-01T00:00:00Z",
                                "end_time": "2026-10-01T00:00:00Z",
                            }
                        ]
                    )
                )
            if path.endswith("/options"):
                return self.send(
                    json.dumps(
                        {
                            "stations": ["Hemming"],
                            "models": ["SUV", "Sedan"],
                            "shifts": [],
                            "shifts_truncated": False,
                        }
                    )
                )
            if path == "/api/investigations":
                rows = [
                    {
                        "id": identifier,
                        "dataset_id": "fixture",
                        "recorded_at": "2026-11-08T12:00:00Z",
                        "question": result["question"],
                    }
                    for identifier, result in reversed(list(state["rows"].items()))
                ]
                return self.send(json.dumps(rows))
            if path.endswith("/result"):
                identifier = path.split("/")[-2]
                return self.send(json.dumps(state["rows"][identifier]))
            if path.startswith("/api/submissions/"):
                identifier = state["keys"][path.rsplit("/", 1)[-1]]
                return self.send(
                    json.dumps(
                        {
                            "admission": "accepted",
                            "investigation_id": identifier,
                            "worker_active": True,
                        }
                    )
                )
            if path.startswith("/api/investigations/"):
                row = state["rows"][path.rsplit("/", 1)[-1]]
                calls = row.get("polls", 0)
                row["polls"] = calls + 1
                return self.send(
                    json.dumps(
                        {
                            "final_confirmed": calls > 0,
                            "execution": "active" if calls == 0 else "finalized",
                            "outcome": row["outcome"] if calls > 0 else None,
                            "events": [
                                {
                                    "component": "planner",
                                    "status": "completed",
                                    "duration_seconds": 1,
                                }
                            ],
                        }
                    )
                )
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            outcome = (
                payload["question"]
                if payload["question"]
                in ("clarification_required", "unsupported", "incomplete", "failed")
                else "completed"
            )
            identifier = str(uuid4())
            state["posts"] += 1
            state["requests"].append(payload)
            state["rows"][identifier] = deepcopy(browser_result(outcome))
            state["rows"][identifier]["question"] = payload["question"]
            state["rows"][identifier]["scope"] = payload["scope"]
            state["rows"][identifier]["investigation_id"] = identifier
            state["rows"][identifier]["intent"] = {
                "Constraint": "constraint_output_loss",
                "Segments": "segmentation",
                "Causes": "causes",
                "What-if": "what_if",
                "Combined": "combined",
            }.get(payload["question"], "constraint_output_loss")
            if payload["question"] == "Segments":
                state["rows"][identifier]["intent"] = "segmentation"
                state["rows"][identifier]["historical"]["segments"] = [
                    {
                        "key": "model:SUV",
                        "kind": "model",
                        "label": "SUV",
                        "jph": 23.25,
                        "completed": 10461,
                        "scheduled_hours": 450,
                        "leading_candidate": "Framing",
                        "warnings": [],
                    },
                    {
                        "key": "model:Sedan",
                        "kind": "model",
                        "label": "Sedan",
                        "jph": 23.63,
                        "completed": 10635,
                        "scheduled_hours": 450,
                        "leading_candidate": "Framing",
                        "warnings": [],
                    },
                ]
            state["last"] = identifier
            state["keys"][self.headers["X-Submission-Key"]] = identifier
            if payload["question"] == "Causes":
                # Commit succeeded but the browser lost its acceptance response.
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"truncated_response":')
                return
            self.send(json.dumps({"investigation_id": identifier}))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        capture_browser(
            tmp_path,
            f"http://127.0.0.1:{server.server_port}",
            width,
            height,
            f"fixture-{width}",
            "fixture",
        )
        assert state["posts"] == 10
        assert len(state["rows"]) == 10  # New chat never deletes an old audit.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        asset_client.close()


@pytest.mark.skipif(
    not EDGE.exists() or os.getenv("STAGE7_TEST_SAVED_BROWSER") != "1",
    reason="Opt in to existing saved-audit browser acceptance with STAGE7_TEST_SAVED_BROWSER=1",
)
@pytest.mark.parametrize("width,height", [(1440, 1200), (390, 1000)])
@pytest.mark.parametrize(
    "saved_kind",
    [
        "combined",
        "constraint_output_loss",
        "segmentation",
        "causes",
        "what_if",
    ],
)
def test_browser_reads_actual_saved_audit_without_execution(tmp_path, width, height, saved_kind):
    from fastapi.testclient import TestClient

    from bottleneck_analyzer.main import app

    posts = []
    identifier = "b8291895-7348-429e-b84c-fb33992dea4e"
    driver = """
    const pause = () => new Promise(resolve => setTimeout(resolve, 20));
    for(let i=0;i<600;i++) {
      const root=document.querySelector('.turn-result'), text=root?.textContent || '';
      if(root && root.querySelector('[data-value="46.88"]') &&
         root.querySelector('[data-value="46.25588888888889"]') &&
         document.querySelector('.composer-note').textContent.includes('human review')) {
        if(new Date(document.querySelector('#start').value+'Z').toISOString() !==
           '2026-09-01T00:00:00.000Z') throw Error('UTC dataset start shifted');
        if(new Date(document.querySelector('#end').value+'Z').toISOString() !==
           '2026-10-01T00:00:00.000Z') throw Error('UTC dataset end shifted');
        if(getComputedStyle(document.body).margin !== '0px') throw Error('CSS not applied');
        if(getComputedStyle(document.querySelector('.workspace')).display !== 'grid')
          throw Error('Layout CSS not applied');
        if(document.documentElement.scrollWidth > innerWidth) throw Error('Horizontal overflow');
        if(window.__browserErrors.length) throw Error(window.__browserErrors.join('; '));
        document.body.dataset.savedResult='passed'; break;
      }
      await pause();
    }
    """
    if saved_kind != "combined":
        from sqlalchemy import text

        from bottleneck_analyzer.db.session import create_db_engine

        engine = create_db_engine()
        try:
            with engine.connect() as connection:
                identifier = connection.scalar(
                    text(
                        "SELECT id::text FROM investigation_audit "
                        "WHERE state->'response'->>'intent'=:intent "
                        "AND state->'response'->>'outcome'='completed' "
                        "AND state->'response'->>'audit_id'=id::text "
                        "ORDER BY recorded_at DESC LIMIT 1"
                    ),
                    {"intent": saved_kind},
                )
        finally:
            engine.dispose()
        if identifier is None:
            pytest.skip(f"No confirmed saved {saved_kind} investigation exists")
    if saved_kind == "segmentation":
        driver = """
        const pause=()=>new Promise(resolve=>setTimeout(resolve,20));
        for(let i=0;i<600;i++){
          const root=document.querySelector('.turn-result');
          const comparison=root?.querySelector('.answer > .answer-comparison');
          if(comparison){
            if(document.querySelector('.evidence-toggle').open)
              throw Error('Evidence should remain collapsed');
            const result=await (await fetch(location.pathname.replace(/.$/,'/')+
              'api/investigations/'+new URL(location.href).searchParams.get('investigation')+
              '/result')).json();
            for(const model of result.historical.segments.filter(s=>s.kind==='model')){
              if(!comparison.textContent.includes(model.label) ||
                 !comparison.textContent.includes(model.leading_candidate || 'Not established'))
                throw Error('Saved model comparison differs from result');
            }
            if(!root.querySelector('.answer').textContent.includes('dated shifts'))
              throw Error('Shift findings missing from main answer');
            if(document.documentElement.scrollWidth>innerWidth) throw Error('Horizontal overflow');
            if(window.__browserErrors.length) throw Error(window.__browserErrors.join(';'));
            document.body.dataset.savedResult='passed';break;
          }
          await pause();
        }
        """
    if saved_kind == "constraint_output_loss":
        driver = r"""
        const pause=()=>new Promise(resolve=>setTimeout(resolve,20));
        for(let i=0;i<600;i++){
          const details=document.querySelector('.evidence-toggle');
          if(details?.querySelector('.evidence-section')){
            details.open=true;
            const text=details.innerText;
            if(!text.includes('How the output was measured'))
              throw Error('Main bottleneck evidence missing');
            const saved=await (await fetch('/api/investigations/'+
              new URL(location.href).searchParams.get('investigation')+'/result')).json();
            for(const value of [saved.historical.historical_jph, saved.historical.design_gap_jph]){
              if(value!=null && ![...details.querySelectorAll('[data-value]')].some(
                  node=>node.dataset.value===String(value)))
                throw Error('Stored historical figures changed');
            }
            if(saved.historical.supporting_indicators.some(s=>s.startsWith('Input queue')) &&
                !text.includes('Vehicles build up')) throw Error('Queue evidence omitted');
            if(text.split(/\s+/).length>240) throw Error('Evidence is too long');
            if(/[a-f0-9]{8}-[a-f0-9-]{27}/i.test(text)) throw Error('Internal ID displayed');
            for(const phrase of ['state:blocked','0.9998','Saved workflow checkpoints',
                'Executive summary','Historical measurement provenance',
                'No simulation result was returned','No evidence result was returned']){
              if(text.includes(phrase)) throw Error('Technical evidence dump: '+phrase);
            }
            if(document.documentElement.scrollWidth>innerWidth) throw Error('Horizontal overflow');
            if(window.__browserErrors.length) throw Error(window.__browserErrors.join(';'));
            document.body.dataset.savedResult='passed';break;
          }
          await pause();
        }
        """
    if saved_kind in ("causes", "what_if"):
        driver = """
        const pause=()=>new Promise(resolve=>setTimeout(resolve,20));
        for(let i=0;i<600;i++){
          const root=document.querySelector('.turn-result'), answer=root?.querySelector('.answer');
          if(answer?.textContent){
            const text=answer.textContent;
            for(const phrase of ['Historical output:', 'Design gap:', 'supported_hypothesis',
                'Unresolved:', 'Simulated paired means', 'constraint moved: False']){
              if(text.includes(phrase))
                throw Error('Technical boilerplate in main answer: '+phrase);
            }
            const result=await (await fetch('/api/investigations/'+
              new URL(location.href).searchParams.get('investigation')+'/result')).json();
            if(result.intent==='what_if' &&
                !text.includes('simulation estimates output would go from'))
              throw Error('Scenario answer does not lead with the estimated change');
            if(result.intent==='what_if' && !text.includes('95% confidence interval'))
              throw Error('Simulation uncertainty was removed');
            if(result.intent==='causes' && text.includes('bottleneck for this period'))
              throw Error('Cause answer starts with unrelated historical findings');
            if(!root.querySelector('.answer-status').closest('.evidence-toggle'))
              throw Error('Completed metadata clutters the main answer');
            if(document.querySelector('.evidence-toggle').open)
              throw Error('Evidence should remain collapsed');
            if(document.documentElement.scrollWidth>innerWidth) throw Error('Horizontal overflow');
            if(window.__browserErrors.length) throw Error(window.__browserErrors.join(';'));
            document.body.dataset.savedResult='passed';break;
          }
          await pause();
        }
        """
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                posts.append(self.path)
                self.send_response(405)
                self.end_headers()

            def do_GET(self):
                if self.path == "/saved-driver.mjs":
                    content, mime = driver.encode(), "text/javascript"
                elif self.path == "/capture.mjs":
                    content, mime = CAPTURE.encode(), "text/javascript"
                else:
                    response = client.get(self.path)
                    self.send_response(response.status_code)
                    mime = response.headers.get("content-type", "application/json")
                    content = response.content
                    if urlsplit(self.path).path == "/":
                        content = content.replace(
                            b"</body>",
                            b'<script type="module" src="/saved-driver.mjs"></script></body>',
                        )
                        content = content.replace(
                            b'<script type="module"',
                            b'<script src="/capture.mjs"></script><script type="module"',
                            1,
                        )
                    self.send_header("Content-Type", mime)
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header(
                        "Content-Security-Policy",
                        response.headers.get("content-security-policy", "default-src 'self'"),
                    )
                    self.end_headers()
                    self.wfile.write(content)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.end_headers()
                self.wfile.write(content)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            capture_browser(
                tmp_path,
                f"http://127.0.0.1:{server.server_port}/?investigation={identifier}",
                width,
                height,
                f"actual-saved-{saved_kind}-{width}",
                "saved",
            )
            assert not posts
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
