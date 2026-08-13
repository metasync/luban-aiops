I'll analyze the codebase to create comprehensive WebSocket API documentation for real-time streaming capabilities. Let me start by exploring the relevant files and understanding the project structure.

<tool_call>
<function=search_codebase>
<parameter=query>
WebSocket streaming real-time connection authentication handshake
</parameter>
<parameter=key_words>
websocket,streaming,authentication
</parameter>
<parameter=explanation>
Searching for WebSocket-related code to understand the streaming implementation and authentication mechanisms.
</parameter>
</function>
</tool_call>
<tool_call>
<function=search_file>
<parameter=query>
*websocket*.py
</parameter>
<parameter=explanation>
Looking for WebSocket implementation files in the codebase.
</parameter>
</function>
</tool_call>
<tool_call>
<function=search_file>
<parameter=query>
*stream*.py
</parameter>
<parameter=explanation>
Finding stream-related Python files that might contain streaming logic.
</parameter>
</function>
</tool_call>
<tool_call>
<function=grep_code>
<parameter=regex>
websocket|WebSocket|ws://|wss://
</parameter>
<parameter=explanation>
Searching for WebSocket references across all files to identify streaming endpoints.
</parameter>
</function>
</tool_call>