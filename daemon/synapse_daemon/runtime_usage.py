from dataclasses import dataclass
import json
import re

@dataclass
class Usage:
    runtime: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    credits: float = 0.0
    requests: int = 0

def parse_claude(stdout: str) -> Usage:
    usage_obj = Usage(runtime="claude")
    try:
        first_brace = stdout.find('{')
        last_brace = stdout.rfind('}')
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            return usage_obj
        json_str = stdout[first_brace:last_brace+1]
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return usage_obj
        
        # total_cost_usd -> cost_usd
        cost_usd = data.get("total_cost_usd", 0.0)
        try:
            usage_obj.cost_usd = float(cost_usd) if cost_usd is not None else 0.0
        except (ValueError, TypeError):
            usage_obj.cost_usd = 0.0
            
        # usage dictionary
        usage_dict = data.get("usage")
        if isinstance(usage_dict, dict):
            input_tokens = usage_dict.get("input_tokens", 0)
            output_tokens = usage_dict.get("output_tokens", 0)
            cache_creation = usage_dict.get("cache_creation_input_tokens", 0)
            cache_read = usage_dict.get("cache_read_input_tokens", 0)
            
            try:
                usage_obj.input_tokens = int(input_tokens) if input_tokens is not None else 0
            except (ValueError, TypeError):
                usage_obj.input_tokens = 0
                
            try:
                usage_obj.output_tokens = int(output_tokens) if output_tokens is not None else 0
            except (ValueError, TypeError):
                usage_obj.output_tokens = 0
                
            try:
                cc = int(cache_creation) if cache_creation is not None else 0
            except (ValueError, TypeError):
                cc = 0
                
            try:
                cr = int(cache_read) if cache_read is not None else 0
            except (ValueError, TypeError):
                cr = 0
                
            usage_obj.total_tokens = usage_obj.input_tokens + usage_obj.output_tokens + cc + cr
            
        # modelUsage
        model_usage = data.get("modelUsage")
        if isinstance(model_usage, dict):
            max_cost = -1.0
            best_model = ""
            for m_name, m_info in model_usage.items():
                if isinstance(m_info, dict):
                    m_cost = m_info.get("costUSD", 0.0)
                    try:
                        m_cost_f = float(m_cost) if m_cost is not None else 0.0
                    except (ValueError, TypeError):
                        m_cost_f = 0.0
                    if m_cost_f > max_cost:
                        max_cost = m_cost_f
                        best_model = m_name
            usage_obj.model = best_model
            
    except Exception:
        pass
    return usage_obj

def parse_gemini(stdout: str) -> Usage:
    usage_obj = Usage(runtime="gemini")
    try:
        first_brace = stdout.find('{')
        last_brace = stdout.rfind('}')
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            return usage_obj
        json_str = stdout[first_brace:last_brace+1]
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return usage_obj
            
        stats = data.get("stats")
        if isinstance(stats, dict):
            models = stats.get("models")
            if isinstance(models, dict):
                total_input = 0
                total_output = 0
                total_tot = 0
                total_reqs = 0
                max_total_tokens = -1
                best_model = ""
                
                for m_name, m_info in models.items():
                    if not isinstance(m_info, dict):
                        continue
                    
                    # api
                    api = m_info.get("api")
                    reqs = 0
                    if isinstance(api, dict):
                        try:
                            reqs = int(api.get("totalRequests", 0)) if api.get("totalRequests") is not None else 0
                        except (ValueError, TypeError):
                            reqs = 0
                    total_reqs += reqs
                    
                    # tokens
                    tokens = m_info.get("tokens")
                    t_input = 0
                    t_output = 0
                    t_total = 0
                    if isinstance(tokens, dict):
                        try:
                            t_input = int(tokens.get("input", 0)) if tokens.get("input") is not None else 0
                        except (ValueError, TypeError):
                            t_input = 0
                        try:
                            t_output = int(tokens.get("candidates", 0)) if tokens.get("candidates") is not None else 0
                        except (ValueError, TypeError):
                            t_output = 0
                        try:
                            t_total = int(tokens.get("total", 0)) if tokens.get("total") is not None else 0
                        except (ValueError, TypeError):
                            t_total = 0
                            
                    total_input += t_input
                    total_output += t_output
                    total_tot += t_total
                    
                    if t_total > max_total_tokens:
                        max_total_tokens = t_total
                        best_model = m_name
                
                usage_obj.input_tokens = total_input
                usage_obj.output_tokens = total_output
                usage_obj.total_tokens = total_tot
                usage_obj.requests = total_reqs
                usage_obj.model = best_model
    except Exception:
        pass
    return usage_obj

def parse_codex(stdout: str) -> Usage:
    usage_obj = Usage(runtime="codex")
    try:
        match = re.search(r'tokens\s+used', stdout, re.IGNORECASE)
        if match:
            sub = stdout[match.end():]
            direct_match = re.match(r'^[\s:=]*([\d,]+(?:\.\d*)?)', sub)
            if direct_match:
                num_str = direct_match.group(1)
            else:
                any_num_match = re.search(r'([\d,]+(?:\.\d*)?)', sub)
                num_str = any_num_match.group(1) if any_num_match else None
                
            if num_str:
                num_str_clean = num_str.replace(',', '')
                try:
                    usage_obj.total_tokens = int(float(num_str_clean))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return usage_obj

def parse_copilot(stdout: str) -> Usage:
    usage_obj = Usage(runtime="copilot")
    try:
        match = re.search(r'AI\s+Credits', stdout, re.IGNORECASE)
        if match:
            sub = stdout[match.end():]
            direct_match = re.match(r'^[\s:=]*([\d,]+(?:\.\d*)?)', sub)
            if direct_match:
                num_str = direct_match.group(1)
            else:
                any_num_match = re.search(r'([\d,]+(?:\.\d*)?)', sub)
                num_str = any_num_match.group(1) if any_num_match else None
                
            if num_str:
                num_str_clean = num_str.replace(',', '')
                try:
                    usage_obj.credits = float(num_str_clean)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return usage_obj

def parse_usage(runtime: str, stdout: str) -> Usage:
    if not isinstance(stdout, str):
        stdout = ""
    if not isinstance(runtime, str):
        runtime = str(runtime) if runtime is not None else ""
        
    try:
        if runtime == "claude":
            return parse_claude(stdout)
        elif runtime == "gemini":
            return parse_gemini(stdout)
        elif runtime == "codex":
            return parse_codex(stdout)
        elif runtime == "copilot":
            return parse_copilot(stdout)
        else:
            return Usage(runtime=runtime)
    except Exception:
        return Usage(runtime=runtime)

if __name__ == '__main__':
    # Self-test block to verify correct behavior of our parser functions
    
    # Test 1: Claude
    stdout_claude = """
    Warning: something is happening here.
    {"total_cost_usd":0.166,"usage":{"input_tokens":3,"output_tokens":4,
     "cache_creation_input_tokens":27582,"cache_read_input_tokens":0},
     "modelUsage":{"claude-sonnet-4-6":{"costUSD":0.1655},"claude-haiku-4-5":{"costUSD":0.0005}}}
    """
    u_claude = parse_usage("claude", stdout_claude)
    assert u_claude.runtime == "claude"
    assert abs(u_claude.cost_usd - 0.166) < 1e-9
    assert u_claude.input_tokens == 3
    assert u_claude.output_tokens == 4
    assert u_claude.total_tokens == 27589
    assert u_claude.model == "claude-sonnet-4-6"
    assert u_claude.credits == 0.0
    assert u_claude.requests == 0
    
    # Test 2: Gemini
    stdout_gemini = """
    {"stats":{"models":{"gemini-3.5-flash":{"api":{"totalRequests":1},
     "tokens":{"input":8335,"candidates":1,"total":8636,"cached":0}}}}}
    """
    u_gemini = parse_usage("gemini", stdout_gemini)
    assert u_gemini.runtime == "gemini"
    assert u_gemini.input_tokens == 8335
    assert u_gemini.output_tokens == 1
    assert u_gemini.total_tokens == 8636
    assert u_gemini.requests == 1
    assert u_gemini.model == "gemini-3.5-flash"
    assert u_gemini.cost_usd == 0.0
    
    # Test 3: Codex
    u_codex_1 = parse_usage("codex", "tokens used\n20,835")
    assert u_codex_1.runtime == "codex"
    assert u_codex_1.total_tokens == 20835
    
    u_codex_2 = parse_usage("codex", "tokens used: 20,835")
    assert u_codex_2.runtime == "codex"
    assert u_codex_2.total_tokens == 20835
    
    u_codex_3 = parse_usage("codex", "tokens used\n1,200.50")
    assert u_codex_3.runtime == "codex"
    assert u_codex_3.total_tokens == 1200
    
    # Test 4: Copilot
    u_copilot_1 = parse_usage("copilot", "AI Credits 0 (7s)")
    assert u_copilot_1.runtime == "copilot"
    assert u_copilot_1.credits == 0.0
    
    u_copilot_2 = parse_usage("copilot", "AI Credits 1.5")
    assert u_copilot_2.runtime == "copilot"
    assert u_copilot_2.credits == 1.5
    
    # Test 5: Fallbacks and other runtimes
    u_local = parse_usage("local", "any plain text output")
    assert u_local.runtime == "local"
    assert u_local.total_tokens == 0
    assert u_local.cost_usd == 0.0
    
    u_invalid_claude = parse_usage("claude", "{invalid json")
    assert u_invalid_claude.runtime == "claude"
    assert u_invalid_claude.total_tokens == 0
    
    print("All internal assertions passed successfully!")
