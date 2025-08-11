import os, sys, shutil
from datetime import datetime
from fpdf import FPDF, XPos, YPos

def create_final_pdf_report_impl(monthly_reports, config,
                                 create_summary_content_image,
                                 create_mini_equity_pages_images):
    if not monthly_reports:
        print("Tidak ada laporan bulanan untuk dibuat menjadi PDF.", file=sys.stderr)
        return None

    # --- Setup Path & Nama File dengan Pair, Tahun, dan Ekuitas ---
    symbol = config.get('symbol')
    year = config.get('year')
    lot_size = config.get('fixed_lot_size', 0.1)
    initial_balance = int(config.get('initial_balance', 1000))
    use_adx = config.get('use_adx_filter', False)
    use_sl = config.get('use_stop_loss', False)
    wave_period = config.get('wave_period', 36)
    adx_thresh = config.get('adx_threshold', 15)
    sl_pts = config.get('stop_loss_points', 10.0)
    start_time_str = config.get('trade_start_time', '00:00').replace(':', '')
    end_time_str = config.get('trade_end_time', '23:59').replace(':', '')

    if use_adx and use_sl: level1_folder = "ADX_and_SL"
    elif use_adx:          level1_folder = "ADX_Only"
    elif use_sl:           level1_folder = "SL_Only"
    else:                  level1_folder = "NoFilter"

    path_components = [
        'Backtester', 'Hasil Laporan PDF', symbol, str(year), level1_folder,
        f"wave({wave_period})", f"lot({lot_size})"
    ]
    if level1_folder == "ADX_and_SL": path_components.append(f"ADX({adx_thresh})_SL({sl_pts})")
    elif level1_folder == "ADX_Only": path_components.append(f"ADX({adx_thresh})")
    elif level1_folder == "SL_Only":  path_components.append(f"SL({sl_pts})")

    path_components.append(f"{start_time_str}-{end_time_str}")
    output_dir = os.path.join(*path_components)
    os.makedirs(output_dir, exist_ok=True)

    param_str_file = monthly_reports[0]['param_str']
    time_str = monthly_reports[0].get('time_str', '')
    pdf_filename = os.path.join(
        output_dir, f"FINAL_REPORT_{symbol}_E{initial_balance}_{param_str_file}_T{time_str}.pdf"
    )

    # === LANGKAH 1: BUAT GAMBAR KOMPONEN ===
    summary_content_path = os.path.join(output_dir, "temp_summary_content.png")
    create_summary_content_image(monthly_reports, config, summary_content_path)
    mini_curve_image_paths = create_mini_equity_pages_images(monthly_reports, output_dir)

    # siapkan list cleanup
    temp_images_to_delete = [summary_content_path] + list(mini_curve_image_paths)
    made_pdf = False

    try:
        # === LANGKAH 2: RAKIT PDF ===
        pdf = FPDF('P', 'mm', 'A4')

        # Halaman 1
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, 'Halaman 1: Ringkasan Kinerja Strategi',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        if os.path.exists(summary_content_path):
            pdf.image(summary_content_path, x=10, y=25, w=190)

        # Halaman mini-curves
        for img_path in mini_curve_image_paths:
            pdf.add_page()
            pdf.set_font('helvetica', 'B', 16)
            pdf.cell(0, 10, f'Halaman {pdf.page_no()}: Ringkasan Grafik Ekuitas',
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            if os.path.exists(img_path):
                pdf.image(img_path, x=10, y=25, w=190)

        # Detail ekuitas (2 chart/halaman)
        detailed_chart_paths = [
            os.path.join(r['run_directory'], f"equity_curve_{r['period_for_filename']}.png")
            for r in monthly_reports
        ]
        for i in range(0, len(detailed_chart_paths), 2):
            pdf.add_page()
            pdf.set_font('helvetica', 'B', 16)
            month_name1 = datetime.strptime(
                monthly_reports[i]['period_for_filename'].split('_to_')[0], '%Y-%m-%d'
            ).strftime('%B %Y')
            title = f"Detail Ekuitas - {month_name1}"
            if i + 1 < len(detailed_chart_paths):
                month_name2 = datetime.strptime(
                    monthly_reports[i+1]['period_for_filename'].split('_to_')[0], '%Y-%m-%d'
                ).strftime('%B %Y')
                title += f" & {month_name2}"
            pdf.cell(0, 10, f'Halaman {pdf.page_no()}: {title}',
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

            if os.path.exists(detailed_chart_paths[i]):
                pdf.image(detailed_chart_paths[i], x=10, y=30, w=190, h=110)
            if i + 1 < len(detailed_chart_paths) and os.path.exists(detailed_chart_paths[i+1]):
                pdf.image(detailed_chart_paths[i+1], x=10, y=155, w=190, h=110)

        # === LANGKAH 3: SIMPAN PDF ===
        os.makedirs(os.path.dirname(pdf_filename), exist_ok=True)
        pdf.output(pdf_filename)
        made_pdf = True
        print(f"Laporan PDF Lengkap dengan format baru telah disimpan di: {pdf_filename}")
        return pdf_filename

    except Exception as e:
        error_msg = f"GAGAL MEMBUAT LAPORAN PDF. Penyebab: {type(e).__name__} - {e}"
        print(error_msg, file=sys.stderr)
        return None

    finally:
        # === LANGKAH 4: BERSIHKAN FILE SEMENTARA (hanya jika sukses) ===
        if made_pdf:
            for img_path in temp_images_to_delete:
                try:
                    if img_path and os.path.exists(img_path):
                        os.remove(img_path)
                except Exception:
                    pass  # jangan ganggu alur kalau gagal hapus temp

            # Hapus folder chart sementara (bukan folder output PDF)
            charts_directory = monthly_reports[0].get('run_directory')
            try:
                if charts_directory \
                   and os.path.isdir(charts_directory) \
                   and os.path.abspath(charts_directory) != os.path.abspath(os.path.dirname(pdf_filename)):
                    shutil.rmtree(charts_directory)
                    print(f"Folder sementara '{charts_directory}' berhasil dihapus.")
            except Exception as e2:
                print(f"Gagal menghapus folder sementara '{charts_directory}': {e2}", file=sys.stderr)