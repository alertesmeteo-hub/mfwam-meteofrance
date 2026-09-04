<?php
/**
 * Plugin Name: MFWAM Météo-France — Cartes de vagues
 * Plugin URI: https://github.com/alertesmeteo-hub/mfwam-meteofrance
 * Description: Module de cartes interactives du modèle de vagues MFWAM de Météo-France (façade maritime française, résolution 0,025°).
 * Version: 1.4.0
 * Author: Alertes Météo Hub
 * Requires at least: 5.8
 * Requires PHP: 7.4
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

define('MFW_VERSION', '1.4.0');
define('MFW_RELEASE_DATE', '04/09/2026');
define('MFW_OPTION_BASE_URL', 'mfw_national_data_base_url');
define(
    'MFW_DEFAULT_BASE_URL',
    'https://raw.githubusercontent.com/alertesmeteo-hub/mfwam-meteofrance/data'
);

// Auto-guérison du pipeline MFWAM : si index.json est resté bloqué trop
// longtemps (cron GitHub Actions peu fiable), chaque chargement de la page
// relance côté serveur un nouveau run via workflow_dispatch. Le jeton
// GitHub reste EXCLUSIVEMENT côté serveur — à définir dans wp-config.php :
//   define('MFW_GITHUB_TOKEN', 'github_pat_xxx...');
// Jeton « fine-grained », limité au dépôt alertesmeteo-hub/mfwam-meteofrance,
// permission « Actions » en Read and write.
define('MFW_GITHUB_REPO', 'alertesmeteo-hub/mfwam-meteofrance');
define('MFW_GITHUB_DATA_BRANCH', 'data');
define('MFW_GITHUB_WORKFLOW_BRANCH', 'main');
define('MFW_GITHUB_WORKFLOW_FILE', 'update-mfwam.yml');
// MFWAM tourne 4 fois par jour (00/06/12/18 UTC) : seuil resserré à 8 h.
define('MFW_STALE_THRESHOLD_MIN', 8 * 60);

add_action('wp_enqueue_scripts', 'mfw_register_assets');
add_action('admin_init', 'mfw_register_settings');
add_action('admin_menu', 'mfw_add_settings_page');
add_shortcode('mfwam_meteo', 'mfw_render_shortcode');
add_filter('plugin_action_links_' . plugin_basename(__FILE__), 'mfw_plugin_action_links');
add_action('wp_ajax_mfw_autoheal', 'mfw_handle_autoheal');
add_action('wp_ajax_nopriv_mfw_autoheal', 'mfw_handle_autoheal');

function mfw_handle_autoheal() {
    if (!defined('MFW_GITHUB_TOKEN') || !MFW_GITHUB_TOKEN) {
        wp_send_json_success(array('configured' => false));
    }

    if (get_transient('mfw_autoheal_lock')) {
        wp_send_json_success(array('skipped' => true));
    }
    set_transient('mfw_autoheal_lock', 1, 5 * MINUTE_IN_SECONDS);

    $generated_at = mfw_fetch_generated_at();
    if (null === $generated_at) {
        wp_send_json_success(array('configured' => true, 'checked' => false));
    }

    $age_minutes = (time() - $generated_at) / 60;
    if ($age_minutes <= MFW_STALE_THRESHOLD_MIN) {
        wp_send_json_success(array('configured' => true, 'stale' => false, 'age_minutes' => round($age_minutes)));
    }

    if (get_transient('mfw_autoheal_cooldown')) {
        wp_send_json_success(array('configured' => true, 'stale' => true, 'triggered' => false, 'cooldown' => true));
    }
    set_transient('mfw_autoheal_cooldown', 1, 30 * MINUTE_IN_SECONDS);

    $triggered = mfw_trigger_workflow();
    wp_send_json_success(array('configured' => true, 'stale' => true, 'triggered' => $triggered));
}

function mfw_fetch_generated_at() {
    $url = 'https://api.github.com/repos/' . MFW_GITHUB_REPO . '/contents/index.json'
        . '?ref=' . rawurlencode(MFW_GITHUB_DATA_BRANCH);
    $response = wp_remote_get($url, array(
        'headers' => array(
            'Accept'     => 'application/vnd.github.raw',
            'User-Agent' => 'mfwam-meteofrance-france-autoheal',
        ),
        'timeout' => 8,
    ));
    if (is_wp_error($response) || 200 !== wp_remote_retrieve_response_code($response)) {
        return null;
    }
    $data = json_decode(wp_remote_retrieve_body($response), true);
    if (empty($data['generated_at'])) {
        return null;
    }
    $timestamp = strtotime($data['generated_at']);
    return $timestamp ? $timestamp : null;
}

function mfw_trigger_workflow() {
    $url = 'https://api.github.com/repos/' . MFW_GITHUB_REPO . '/actions/workflows/'
        . rawurlencode(MFW_GITHUB_WORKFLOW_FILE) . '/dispatches';
    $response = wp_remote_post($url, array(
        'headers' => array(
            'Accept'        => 'application/vnd.github+json',
            'Authorization' => 'Bearer ' . MFW_GITHUB_TOKEN,
            'Content-Type'  => 'application/json',
            'User-Agent'    => 'mfwam-meteofrance-france-autoheal',
        ),
        'body'    => wp_json_encode(array('ref' => MFW_GITHUB_WORKFLOW_BRANCH)),
        'timeout' => 8,
    ));
    if (is_wp_error($response)) {
        return false;
    }
    $code = wp_remote_retrieve_response_code($response);
    return $code >= 200 && $code < 300;
}

function mfw_plugin_action_links($links) {
    $settings_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=mfwam-meteofrance')),
        esc_html__('Réglages', 'mfwam-meteofrance')
    );
    array_unshift($links, $settings_link);

    $help_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=mfwam-meteofrance')),
        esc_html__('Shortcodes / Aide', 'mfwam-meteofrance')
    );
    array_unshift($links, $help_link);

    return $links;
}

function mfw_register_assets() {
    wp_register_style(
        'mfw-map',
        plugin_dir_url(__FILE__) . 'assets/mfwam-map.css',
        array(),
        MFW_VERSION
    );
    wp_register_script(
        'mfw-map',
        plugin_dir_url(__FILE__) . 'assets/mfwam-map.js',
        array(),
        MFW_VERSION,
        true
    );
    wp_localize_script('mfw-map', 'MFW_AUTOHEAL', array(
        'url' => admin_url('admin-ajax.php?action=mfw_autoheal'),
    ));
}

function mfw_register_settings() {
    register_setting(
        'mfw_settings',
        MFW_OPTION_BASE_URL,
        array(
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => MFW_DEFAULT_BASE_URL,
        )
    );

    add_settings_section(
        'mfw_main_section',
        'Source des données MFWAM',
        '__return_false',
        'mfwam-meteofrance'
    );

    add_settings_field(
        'mfw_data_base_url_field',
        'Adresse du dossier de données',
        'mfw_render_url_field',
        'mfwam-meteofrance',
        'mfw_main_section'
    );
}

function mfw_render_url_field() {
    $value = get_option(MFW_OPTION_BASE_URL, MFW_DEFAULT_BASE_URL);
    printf(
        '<input type="url" class="regular-text code" name="%1$s" value="%2$s" autocomplete="off">',
        esc_attr(MFW_OPTION_BASE_URL),
        esc_attr($value)
    );
    echo '<p class="description">Conservez l’adresse proposée : elle pointe vers la branche « data » du dépôt MFWAM.</p>';
}

function mfw_add_settings_page() {
    add_options_page(
        'Cartes MFWAM Météo-France',
        'MFWAM Météo-France',
        'manage_options',
        'mfwam-meteofrance',
        'mfw_render_settings_page'
    );
}

function mfw_render_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>MFWAM Météo-France — Cartes de vagues</h1>
        <form action="options.php" method="post">
            <?php
            settings_fields('mfw_settings');
            do_settings_sections('mfwam-meteofrance');
            submit_button();
            ?>
        </form>
        <p><strong>Version du module : <?php echo esc_html(MFW_VERSION); ?> (<?php echo esc_html(MFW_RELEASE_DATE); ?>)</strong></p>
        <h2>Shortcode unique</h2>
        <p><code>[mfwam_meteo]</code> : carte interactive des vagues (11 couches — vent et houle).</p>
        <p><code>[mfwam_meteo variable="hauteur_houle_totale" hauteur="700" titre="Vagues — Manche et Atlantique"]</code></p>
        <p>
            Non disponibles dans le paquet ouvert Météo-France SP1 (données non publiées) : indice
            Benjamin-Feir, hauteur maximale individuelle, période de la hauteur maximale.
        </p>
        <h2>Auto-guérison du pipeline</h2>
        <p>
            Statut : <strong><?php echo (defined('MFW_GITHUB_TOKEN') && MFW_GITHUB_TOKEN) ? '✅ Configurée' : '⚠️ Non configurée'; ?></strong>
        </p>
        <p>
            Si <code>index.json</code> reste bloqué plus de <?php echo esc_html((int) round(MFW_STALE_THRESHOLD_MIN / 60)); ?> heures,
            chaque chargement de cette page relance automatiquement le pipeline sur GitHub. Pour l'activer, ajouter dans
            <code>wp-config.php</code> :
        </p>
        <p><code>define('MFW_GITHUB_TOKEN', 'github_pat_xxx...');</code></p>
        <p>
            Jeton « fine-grained » GitHub, limité au dépôt <code>alertesmeteo-hub/mfwam-meteofrance</code>, permission
            « Actions : Read and write » uniquement. Il n'est jamais transmis au navigateur.
        </p>
    </div>
    <?php
}

function mfw_base_url() {
    $url = get_option(MFW_OPTION_BASE_URL, MFW_DEFAULT_BASE_URL);
    return untrailingslashit(apply_filters('mfw_national_data_base_url', $url));
}

function mfw_map_variable($value) {
    $variable = strtolower(trim(sanitize_key((string) $value)));
    $allowed = array(
        'hauteur_significative',
        'hauteur_mer_du_vent',
        'periode_moyenne',
        'periode_mer_du_vent',
        'hauteur_houle_totale',
        'hauteur_houle_primaire',
        'hauteur_houle_secondaire',
        'periode_houle_totale',
        'periode_houle_primaire',
        'periode_houle_secondaire',
        'periode_pic',
    );
    return in_array($variable, $allowed, true) ? $variable : 'hauteur_significative';
}

function mfw_render_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'variable' => 'hauteur_significative',
            'hauteur' => '900',
            'titre' => 'Cartes MFWAM — vagues et houle',
            'animation' => 'oui',
        ),
        $atts,
        'mfwam_meteo'
    );

    $variable = mfw_map_variable($atts['variable']);
    $height = max(440, min(1300, absint($atts['hauteur'])));
    $title = trim(sanitize_text_field($atts['titre']));
    if ($title === '') {
        $title = 'Cartes MFWAM — vagues et houle';
    }
    $animation_value = strtolower(trim(sanitize_text_field($atts['animation'])));
    $animation = !in_array($animation_value, array('non', '0', 'false', 'off'), true);
    $map_id = function_exists('wp_unique_id')
        ? wp_unique_id('mfw-map-')
        : 'mfw-map-' . wp_rand(1000, 999999);

    wp_enqueue_style('mfw-map');
    wp_enqueue_script('mfw-map');

    ob_start();
    ?>
    <section
        id="<?php echo esc_attr($map_id); ?>"
        class="mfw-card mfwm-card"
        data-mfwm-app
        data-base-url="<?php echo esc_url(mfw_base_url()); ?>"
        data-variable="<?php echo esc_attr($variable); ?>"
        data-timezone="<?php echo esc_attr(wp_timezone_string()); ?>"
        data-animation="<?php echo $animation ? '1' : '0'; ?>"
        data-module-version="<?php echo esc_attr(MFW_VERSION); ?>"
        style="--mfwm-height: <?php echo esc_attr($height); ?>px"
    >
        <header class="mfw-header mfwm-header">
            <div>
                <p class="mfw-kicker">MODÈLE DE VAGUES • FAÇADE FRANÇAISE • ÉCHÉANCES HORAIRES</p>
                <h2><?php echo esc_html($title); ?></h2>
                <p class="mfw-meta" data-mfwm-run>Chargement du dernier run MFWAM…</p>
            </div>
            <div class="mfw-badge">MFWAM<br><strong>0,025°</strong></div>
        </header>

        <div class="mfwm-toolbar-sentinel" data-mfwm-toolbar-sentinel></div>
        <div class="mfwm-toolbar" data-mfwm-toolbar>
            <div class="mfwm-field mfwm-layer-picker">
                <span>Paramètre</span>
                <strong class="mfwm-layer-trigger" data-mfwm-current-layer>Hauteur significative des vagues</strong>
            </div>
            <div class="mfwm-time-controls" aria-label="Navigation dans les échéances">
                <button type="button" data-mfwm-previous title="Échéance précédente" aria-label="Échéance précédente">◀</button>
                <button type="button" data-mfwm-play title="Lancer l’animation" aria-label="Lancer l’animation">▶</button>
                <button type="button" data-mfwm-next title="Échéance suivante" aria-label="Échéance suivante">▶</button>
            </div>
            <div class="mfwm-validity">
                <span>Prévision valable</span>
                <strong data-mfwm-validity>—</strong>
                <small data-mfwm-lead>—</small>
            </div>
        </div>

        <div
            id="<?php echo esc_attr($map_id . '-layers'); ?>"
            class="mfwm-layer-menu"
            data-mfwm-layer-menu
        >
            <div class="mfwm-layer-menu-head">
                <div>
                    <strong>Choisir une carte MFWAM</strong>
                    <small>Paramètres du paquet SP1 disponibles dans cette première version</small>
                </div>
            </div>
            <div class="mfwm-layer-grid" data-mfwm-layer-grid></div>
        </div>

        <p class="mfw-stale" data-mfwm-stale role="status" hidden>
            Attention : la dernière production disponible a plus de 8 heures.
        </p>

        <div class="mfwm-viewport" data-mfwm-viewport role="img" aria-label="Carte des vagues MFWAM interactive">
            <div class="mfwm-scene" data-mfwm-scene>
                <img class="mfwm-background" data-mfwm-background alt="" aria-hidden="true">
                <img class="mfwm-layer-image" data-mfwm-layer-image alt="">
            </div>
            <div class="mfwm-map-titlebar">
                <strong data-mfwm-map-title>Carte MFWAM</strong>
                <span data-mfwm-map-run>Run MFWAM —</span>
            </div>
            <div class="mfwm-map-date" data-mfwm-map-date>Échéance —</div>
            <div class="mfwm-map-buttons" aria-label="Commandes de zoom">
                <span class="mfwm-zoom-level" data-mfwm-zoom-level>100 %</span>
                <button type="button" data-mfwm-zoom-in title="Agrandir" aria-label="Agrandir">+</button>
                <button type="button" data-mfwm-zoom-out title="Réduire" aria-label="Réduire">−</button>
                <button type="button" data-mfwm-reset title="Recentrer" aria-label="Recentrer">⌂</button>
                <button type="button" data-mfwm-fullscreen title="Plein écran" aria-label="Plein écran">⛶</button>
            </div>
            <div class="mfwm-legend" data-mfwm-legend aria-label="Légende de la carte"></div>
            <div class="mfwm-probe" data-mfwm-probe hidden></div>
            <a class="mfwm-map-brand" href="https://www.alertes-meteo.com/" target="_blank" rel="noopener noreferrer">
                www.alertes-meteo.com • Module v<?php echo esc_html(MFW_VERSION); ?> (<?php echo esc_html(MFW_RELEASE_DATE); ?>)
            </a>
            <div class="mfwm-loading" data-mfwm-loading role="status">Chargement de la carte…</div>
            <div class="mfwm-error" data-mfwm-error role="alert" hidden></div>
        </div>

        <div class="mfwm-timeline" data-mfwm-timeline>
            <input data-mfwm-slider type="range" min="0" max="0" value="0" step="1" aria-label="Échéance de prévision">
            <div class="mfwm-timeline-labels"><span>Run</span><span>Échéance maximale</span></div>
        </div>

        <footer class="mfw-footer">
            <span data-mfwm-generated>Mise à jour en cours de lecture…</span>
            <span>
                Données météo directes :
                <a href="https://www.data.gouv.fr/datasets/paquets-de-modele-de-vagues-mfwam-resolution-0-025deg" target="_blank" rel="noopener noreferrer">MFWAM 0,025° — Météo-France</a>
                • <a href="https://www.alertes-meteo.com/" target="_blank" rel="noopener noreferrer">www.alertes-meteo.com</a>
                • Module cartes v<?php echo esc_html(MFW_VERSION); ?> (<?php echo esc_html(MFW_RELEASE_DATE); ?>)
            </span>
        </footer>

        <noscript>
            <p class="mfw-message mfw-error">JavaScript doit être activé pour afficher les cartes.</p>
        </noscript>
    </section>
    <?php
    return ob_get_clean();
}
