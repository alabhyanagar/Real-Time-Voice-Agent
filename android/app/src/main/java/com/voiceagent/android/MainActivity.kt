package com.voiceagent.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    private val runtimePermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val permissions = buildList {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                add(Manifest.permission.RECORD_AUDIO)
            }
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        if (permissions.isNotEmpty()) {
            runtimePermissions.launch(permissions.toTypedArray())
        }
        setContent {
            VoiceAgentScreen(
                onLaunchDialer = { phoneNumber ->
                    val dialIntent = Intent(Intent.ACTION_DIAL).apply {
                        data = Uri.parse("tel:$phoneNumber")
                    }
                    startActivity(dialIntent)
                }
            )
        }
    }
}

@Composable
private fun VoiceAgentScreen(
    model: VoiceSessionViewModel = viewModel(),
    onLaunchDialer: (String) -> Unit = {}
) {
    val state by model.state.collectAsState()

    LaunchedEffect(Unit) {
        model.effects.collect { effect ->
            when (effect) {
                is VoiceUiEffect.LaunchDialer -> onLaunchDialer(effect.phoneNumber)
            }
        }
    }

    MaterialTheme {
        Column(
            Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text("Voice Agent", style = MaterialTheme.typography.headlineMedium)
            Text("State: ${state.assistantState}")
            Text("Connection: ${state.status}")
            if (state.transcript.isNotBlank()) Text("You: ${state.transcript}")
            if (state.response.isNotBlank()) Text("Agent: ${state.response}")
            if (state.toolStatus.isNotBlank()) Text("Tool: ${state.toolStatus}")
            if (state.telemetry.isNotBlank()) {
                Text("Telemetry: ${state.telemetry}", style = MaterialTheme.typography.labelSmall)
            }
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = {
                    if (state.status == "Connected") model.stop() else model.connect()
                }) {
                    Text(if (state.status == "Connected") "Disconnect" else "Connect")
                }
                OutlinedButton(onClick = { model.setMuted(!state.muted) }) {
                    Text(if (state.muted) "Unmute" else "Mute")
                }
                if (state.status == "Connected") {
                    FilledTonalButton(onClick = { model.cancelActiveTurn() }) {
                        Text("Interrupt")
                    }
                }
            }

            state.confirmationPrompt?.let { prompt ->
                AlertDialog(
                    onDismissRequest = { model.confirmTool(false) },
                    title = { Text("Confirm Tool Action") },
                    text = { Text(prompt) },
                    confirmButton = {
                        TextButton(onClick = { model.confirmTool(true) }) { Text("Approve") }
                    },
                    dismissButton = {
                        TextButton(onClick = { model.confirmTool(false) }) { Text("Decline") }
                    },
                )
            }

            state.dialerTarget?.let { target ->
                AlertDialog(
                    onDismissRequest = { model.confirmDialerCall(false) },
                    title = { Text("Initiate Phone Call") },
                    text = { Text("Do you want to open the native phone dialer to call $target?") },
                    confirmButton = {
                        TextButton(onClick = { model.confirmDialerCall(true) }) { Text("Call") }
                    },
                    dismissButton = {
                        TextButton(onClick = { model.confirmDialerCall(false) }) { Text("Cancel") }
                    },
                )
            }
        }
    }
}
