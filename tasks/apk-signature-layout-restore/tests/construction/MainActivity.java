package com.fieldfolio.mobile.preview;

import android.app.Activity;
import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(48, 64, 48, 32);
        TextView heading = new TextView(this);
        heading.setText("Fieldfolio");
        heading.setTextSize(28);
        layout.addView(heading);
        TextView status = new TextView(this);
        status.setText("Your documents are available on this device. Sign in to sync your projects.");
        status.setTextSize(16);
        layout.addView(status);
        setContentView(layout);
    }
}
