import re
import time
import uuid
from typing import Dict, List, Optional
from ..llm.provider import BaseLLMClient, ChatMessage, LLMResponse, ToolCall
from ..tools.base import BaseTool, ToolResult
from ..logger.audit import AuditLogger
from .models import AgentRunResult, AgentStep
from .prompt import SYSTEM_SRE_PROMPT


class AgentLoop:
    """Orchestrates ReAct agent loop: Reason -> Act -> Observe -> Self-Correct -> Reflect."""

    def __init__(
        self,
        llm: BaseLLMClient,
        tools: List[BaseTool],
        audit_logger: AuditLogger,
        max_steps: int = 6,
        system_prompt: str = SYSTEM_SRE_PROMPT,
    ):
        self.llm = llm
        self.tools: Dict[str, BaseTool] = {t.name: t for t in tools}
        self.tools_schema = [t.to_schema() for t in tools]
        self.audit = audit_logger
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    async def run(self, query: str, session_id: Optional[str] = None) -> AgentRunResult:
        """Executes the autonomous agent loop for a user query."""
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        start_time = time.perf_counter()

        self.audit.log(sess_id, step=0, event_type="start", data={"query": query})

        messages: List[ChatMessage] = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=query),
        ]

        steps: List[AgentStep] = []
        citations: List[str] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        final_answer = ""
        current_step = 1

        while current_step <= self.max_steps:
            step_start = time.perf_counter()

            # 1. Reason: LLM invocation
            llm_resp: LLMResponse = await self.llm.chat(
                messages=messages,
                tools=self.tools_schema,
            )

            total_prompt_tokens += llm_resp.prompt_tokens
            total_completion_tokens += llm_resp.completion_tokens

            # Check for text-based citations in LLM response
            found_citations = re.findall(r"\[[a-zA-Z0-9_\-\.]+#L\d+(?:-L\d+)?\]", llm_resp.content)
            for c in found_citations:
                if c not in citations:
                    citations.append(c)

            # If no tool calls were requested, the model provided its final response
            if not llm_resp.tool_calls:
                final_answer = llm_resp.content
                step = AgentStep(
                    step_number=current_step,
                    thought=llm_resp.content,
                    duration_ms=round((time.perf_counter() - step_start) * 1000, 2),
                )
                steps.append(step)

                self.audit.log(
                    sess_id,
                    step=current_step,
                    event_type="finish",
                    data={"final_answer": final_answer},
                )
                break

            # 2. Act: process each tool call
            for tc in llm_resp.tool_calls:
                tool_name = tc.name
                tool_args = tc.arguments
                was_corrected = False

                self.audit.log(
                    sess_id,
                    step=current_step,
                    event_type="tool_call",
                    data={"tool": tool_name, "arguments": tool_args},
                )

                tool = self.tools.get(tool_name)
                if not tool:
                    observation = ToolResult(
                        tool_name=tool_name,
                        success=False,
                        output="",
                        error=f"Tool '{tool_name}' is not recognized. Permitted tools: {list(self.tools.keys())}",
                    )
                    was_corrected = True
                else:
                    try:
                        observation = await tool.execute(**tool_args)
                    except Exception as exc:
                        observation = ToolResult(
                            tool_name=tool_name,
                            success=False,
                            output="",
                            error=f"Tool execution exception: {str(exc)}",
                        )
                        was_corrected = True

                # 3. Observe & Check for Self-Correction
                if not observation.success:
                    was_corrected = True
                    self.audit.log(
                        sess_id,
                        step=current_step,
                        event_type="self_correction",
                        data={
                            "failed_tool": tool_name,
                            "error": observation.error,
                            "notice": "Error passed back to agent for self-correction.",
                        },
                    )

                # Collect citations if RAG tool was called
                if "citations" in observation.metadata:
                    for cit in observation.metadata["citations"]:
                        if cit not in citations:
                            citations.append(cit)

                # Record step
                step = AgentStep(
                    step_number=current_step,
                    thought=llm_resp.content,
                    tool_call=tc,
                    observation=observation,
                    duration_ms=round((time.perf_counter() - step_start) * 1000, 2),
                    was_corrected=was_corrected,
                )
                steps.append(step)

                self.audit.log(
                    sess_id,
                    step=current_step,
                    event_type="tool_result",
                    data={
                        "tool": tool_name,
                        "success": observation.success,
                        "output_preview": observation.output[:200],
                        "error": observation.error,
                    },
                )

                # Update conversation history with assistant message and tool response
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=llm_resp.content,
                        tool_calls=[tc],
                    )
                )

                tool_obs_content = observation.to_observation_text()
                if was_corrected:
                    tool_obs_content += (
                        "\n[SYSTEM NOTICE: This step failed. Analyze the error above, "
                        "correct your parameters, or choose an alternative diagnostic command.]"
                    )

                messages.append(
                    ChatMessage(
                        role="tool",
                        name=tool_name,
                        content=tool_obs_content,
                    )
                )

            current_step += 1

        # If loop ended without explicit final answer
        if not final_answer:
            if steps and steps[-1].observation:
                final_answer = (
                    f"Диагностический цикл завершён. Последний результат:\n"
                    f"{steps[-1].observation.output}"
                )
            else:
                final_answer = "Диагностика выполнена. Все шаги зафиксированы в журнале аудита."

        total_elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return AgentRunResult(
            session_id=sess_id,
            query=query,
            final_answer=final_answer,
            steps=steps,
            citations=citations,
            success=True,
            total_duration_ms=total_elapsed_ms,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
        )
