package com.dtc.knowledgegraph

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.Bundle
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * DTC Knowledge Graph - Galaxy Mobile Hybrid Activity
 * Adheres to Clean Architecture, SOLID principles, and user-defined Rule 1.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var layoutError: LinearLayout
    private lateinit var tvCurrentServer: TextView
    private lateinit var btnRetry: Button
    private lateinit var btnChangeIp: Button

    private lateinit var prefs: SharedPreferences
    private var currentUrl: String = ""

    companion object {
        private const val PREFS_NAME = "dtc_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val DEFAULT_URL = "http://172.30.1.86:5050"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initPreferences()
        initViews()
        setupWebView()
        setupListeners()
        setupBackNavigation()

        loadServerUrl(currentUrl)
    }

    private fun initPreferences() {
        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        currentUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_URL) ?: DEFAULT_URL
    }

    private fun initViews() {
        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefreshLayout)
        progressBar = findViewById(R.id.progressBar)
        layoutError = findViewById(R.id.layoutError)
        tvCurrentServer = findViewById(R.id.tvCurrentServer)
        btnRetry = findViewById(R.id.btnRetry)
        btnChangeIp = findViewById(R.id.btnChangeIp)

        swipeRefresh.setColorSchemeResources(R.color.primary)
        tvCurrentServer.text = currentUrl
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        configureWebSettings(webView.settings)
        configureWebViewClients()
    }

    private fun configureWebSettings(settings: WebSettings) {
        settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }
    }

    private fun configureWebViewClients() {
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                progressBar.visibility = View.VISIBLE
                layoutError.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                progressBar.visibility = View.GONE
                swipeRefresh.isRefreshing = false
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    progressBar.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                    layoutError.visibility = View.VISIBLE
                    tvCurrentServer.text = currentUrl
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
                if (newProgress >= 100) {
                    progressBar.visibility = View.GONE
                }
            }
        }
    }

    private fun setupListeners() {
        swipeRefresh.setOnRefreshListener {
            loadServerUrl(currentUrl)
        }

        btnRetry.setOnClickListener {
            loadServerUrl(currentUrl)
        }

        btnChangeIp.setOnClickListener {
            showChangeIpDialog()
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    private fun loadServerUrl(url: String) {
        val normalized = normalizeServerUrl(url)
        currentUrl = normalized
        prefs.edit().putString(KEY_SERVER_URL, currentUrl).apply()
        tvCurrentServer.text = currentUrl
        layoutError.visibility = View.GONE
        webView.loadUrl(currentUrl)
    }

    /**
     * URL Normalization helper: Ensures protocol prefix and eliminates trailing slashes
     */
    private fun normalizeServerUrl(rawUrl: String): String {
        val trimmed = rawUrl.trim()
        if (trimmed.isEmpty()) return DEFAULT_URL

        val withProtocol = if (!trimmed.startsWith("http://", ignoreCase = true) &&
            !trimmed.startsWith("https://", ignoreCase = true)
        ) {
            "http://$trimmed"
        } else {
            trimmed
        }
        return withProtocol.removeSuffix("/")
    }

    private fun showChangeIpDialog() {
        val input = EditText(this).apply {
            setText(currentUrl)
            setSelection(text.length)
            hint = getString(R.string.change_server_ip_hint)
        }

        AlertDialog.Builder(this)
            .setTitle(getString(R.string.change_server_ip))
            .setMessage(getString(R.string.change_server_ip_message))
            .setView(input)
            .setPositiveButton(getString(R.string.connect)) { _, _ ->
                val inputUrl = input.text.toString().trim()
                if (inputUrl.isNotEmpty()) {
                    val targetUrl = normalizeServerUrl(inputUrl)
                    loadServerUrl(targetUrl)
                    Toast.makeText(
                        this,
                        getString(R.string.connecting_to_server, targetUrl),
                        Toast.LENGTH_SHORT
                    ).show()
                } else {
                    Toast.makeText(
                        this,
                        getString(R.string.invalid_server_url),
                        Toast.LENGTH_SHORT
                    ).show()
                }
            }
            .setNegativeButton(getString(R.string.cancel), null)
            .show()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        webView.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}
